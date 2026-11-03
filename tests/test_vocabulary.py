from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from app.database.db import make_engine
from app.main import create_app
from app.services import clock
from tests.test_learning import start, exercises, ANSWERS


def unlock(client):
    run = start(client)
    for exercise, answer in zip(exercises(client), ANSWERS):
        response = client.post(f"/api/runs/{run['id']}/answers", json={'exercise_id':exercise['id'], 'answer':answer})
        assert response.status_code == 200
    word = next(w for w in client.get('/api/vocabulary').json()['words'] if w['unlocked'])
    assert client.post(f"/api/vocabulary/{word['id']}/add").status_code == 200
    return word


def test_words_are_not_marked_learned_without_completing_a_lesson(client):
    data = client.get('/api/vocabulary').json()
    assert len(data['words']) == 20
    assert data['added_count'] == data['due_count'] == 0
    assert not any(w['unlocked'] for w in data['words'])
    assert client.post(f"/api/vocabulary/{data['words'][0]['id']}/add").status_code == 409
    assert client.post('/api/vocabulary/999/add').status_code == 404


def test_review_is_idempotent_and_cannot_be_farmed(client, database, monkeypatch):
    monkeypatch.setattr(clock, 'now', lambda: datetime.fromisoformat('2026-11-02T19:01:00+00:00'))
    word = unlock(client)
    url = f"/api/vocabulary/{word['id']}/review"
    body = {'request_id':str(uuid4()), 'answer':word['term'].upper()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=body), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()['due_on'] == '2026-11-04'
    assert client.post(url, json={**body, 'answer':'wrong'}).status_code == 409
    assert client.post(url, json={**body, 'request_id':str(uuid4())}).status_code == 409
    before = client.get('/api/vocabulary').json()
    assert before['due_count'] == 0
    assert next(w for w in before['words'] if w['id'] == word['id'])['review_count'] == 1
    assert client.post(f"/api/vocabulary/{word['id']}/add").json() == before
    assert client.get('/api/dashboard').json()['total_xp'] == 60
    engine = make_engine('sqlite:///' + database.as_posix())
    with TestClient(create_app(engine)) as restarted:
        assert restarted.get('/api/vocabulary').json() == before
    engine.dispose()


def test_spaced_intervals_reset_after_error_and_reviews_count_for_streak(client, monkeypatch):
    moment = datetime.fromisoformat('2026-11-02T07:00:00+00:00')
    monkeypatch.setattr(clock, 'now', lambda: moment)
    word = unlock(client)
    url = f"/api/vocabulary/{word['id']}/review"
    for days in (1, 3, 7, 14, 30, 30):
        result = client.post(url, json={'request_id':str(uuid4()), 'answer':word['term']}).json()
        assert result['is_correct']
        assert result['due_on'] == (clock.local_day() + timedelta(days=days)).isoformat()
        moment += timedelta(days=days)
    wrong = client.post(url, json={'request_id':str(uuid4()), 'answer':'I forgot'}).json()
    assert wrong['is_correct'] is False and wrong['box'] == 0
    assert wrong['correct_answer'] == word['term']
    assert wrong['due_on'] == (clock.local_day()+timedelta(days=1)).isoformat()
    moment += timedelta(days=1)
    assert client.get('/api/vocabulary').json()['due_count'] == 1
    result = client.post(url, json={'request_id':str(uuid4()), 'answer':word['term']}).json()
    assert result['box'] == 1
    stats = client.get('/api/dashboard').json()
    assert stats['current_streak'] == 2
    assert stats['activity'][-1]['vocabulary_reviews'] == 1
    assert stats['total_xp'] == 60
    assert stats['answers'] == 6  # Vocabulary does not inflate exercise accuracy.


def test_client_cannot_supply_review_correctness_or_interval(client):
    word = unlock(client)
    url = f"/api/vocabulary/{word['id']}/review"
    for extra in ({'is_correct':True}, {'box':5}, {'due_on':'2030-01-01'}):
        assert client.post(url, json={'request_id':str(uuid4()), 'answer':'wrong', **extra}).status_code == 422
    for answer in ('', '  ', 'x'*101):
        assert client.post(url, json={'request_id':str(uuid4()), 'answer':answer}).status_code == 422
