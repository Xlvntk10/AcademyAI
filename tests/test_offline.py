import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from tests.test_learning import SLUG, ANSWERS


def submission(client, slug=SLUG):
    response = client.get(f"/api/offline/lessons/{slug}")
    assert response.status_code == 200
    bundle = response.json()
    now = datetime.now(timezone.utc)
    return dict(protocol=1, attempt_id=str(uuid4()), server_id=bundle["server_id"], lesson_slug=slug,
        content_version=bundle["lesson"]["version"], content_hash=bundle["content_hash"],
        started_at=(now-timedelta(hours=2)).isoformat(), completed_at=(now-timedelta(hours=1)).isoformat(),
        answers=[dict(exercise_id=e["id"], answer=a) for e, a in zip(bundle["lesson"]["exercises"], ANSWERS)])


def test_offline_atomic_retry_concurrency_and_xp(client, database):
    bundle = client.get(f"/api/offline/lessons/{SLUG}")
    assert bundle.headers["cache-control"] == "no-store"
    assert "correct_answer" not in bundle.text and "accepted_answers" not in bundle.text
    payload = submission(client)
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _: client.post('/api/offline/attempts', json=payload), range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json() == responses[0].json() for r in responses)
    assert responses[0].json()["result"]["score"] == 60
    assert client.get('/api/progress').json()["total_xp"] == 60
    repeated = copy.deepcopy(payload)
    repeated["attempt_id"] = str(uuid4())
    assert client.post('/api/offline/attempts', json=repeated).status_code == 200
    assert client.get('/api/progress').json()["total_xp"] == 60
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT count(*) FROM offlinereceipt').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM attempt').fetchone()[0] == 12
        assert db.execute('SELECT count(*) FROM lessonrun').fetchone()[0] == 2
    changed = copy.deepcopy(payload)
    changed["answers"][0]["answer"] = "study"
    assert client.post('/api/offline/attempts', json=changed).status_code == 409
    assert client.post('/api/offline/attempts', json=payload).json() == responses[0].json()


def test_offline_rejects_conflicts_and_rolls_back(client, database):
    payload = submission(client)
    for field, value, status in [("content_version", 999, 409), ("content_hash", "0"*64, 409),
                                 ("server_id", str(uuid4()), 409), ("score", 999, 422)]:
        altered = {**payload, field: value}
        assert client.post('/api/offline/attempts', json=altered).status_code == status
    invalid = copy.deepcopy(payload)
    invalid["answers"][-1]["answer"] = "not one of the options"
    assert client.post('/api/offline/attempts', json=invalid).status_code == 422
    for answers in [payload["answers"][:-1], [payload["answers"][0]]*6]:
        assert client.post('/api/offline/attempts', json={**payload, "answers": answers}).status_code == 422
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT count(*) FROM attempt').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM lessonrun').fetchone()[0] == 0
    # An already accepted receipt remains replayable even after a content update.
    response = client.post('/api/offline/attempts', json=payload)
    with sqlite3.connect(database) as db:
        db.execute('UPDATE lessoncontent SET version=version+1 WHERE slug=?', (SLUG,))
    assert client.post('/api/offline/attempts', json=payload).json() == response.json()


def test_offline_keeps_online_run_and_enforces_unlock(client, database):
    payload = submission(client)
    online = client.post(f'/api/lessons/{SLUG}/runs', json={'request_id': str(uuid4())}).json()
    conflict = {**payload, 'attempt_id': online['id']}
    assert client.post('/api/offline/attempts', json=conflict).status_code == 409
    assert client.post('/api/offline/attempts', json=payload).status_code == 200
    assert client.get(f'/api/runs/{online["id"]}').json()['completed_at'] is None
    locked = next(l for l in client.get('/api/lessons').json() if not l['unlocked'])
    assert client.post('/api/offline/attempts', json=submission(client, locked['slug'])).status_code == 409


def test_offline_validates_client_time(client):
    payload = submission(client)
    future = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    assert client.post('/api/offline/attempts', json={**payload, 'completed_at': future}).status_code == 422
    assert client.post('/api/offline/attempts', json={**payload, 'completed_at': '2020-01-01T00:00:00Z'}).status_code == 422
    assert client.post('/api/offline/attempts', json={**payload, 'started_at': '2026-01-01T00:00:00'}).status_code == 422
