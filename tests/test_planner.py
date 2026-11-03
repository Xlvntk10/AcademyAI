from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from app.services import clock
from app.database.db import make_engine
from app.database.models import StudyTask, TaskMove


def freeze(monkeypatch, value="2026-11-02T07:00:00+00:00"):
    monkeypatch.setattr(clock, "now", lambda: datetime.fromisoformat(value))


def generate(client):
    response = client.post('/api/planner/generate', json={"week_start": "2026-11-02"})
    assert response.status_code == 200, response.text
    return response.json()


def test_week_distribution_and_repeat_are_stable(client, monkeypatch):
    freeze(monkeypatch)
    data = generate(client)
    assert data['generated']
    assert data['planned_minutes'] == 810
    assert len(data['tasks']) == len(generate(client)['tasks'])
    for offset in range(7):
        day = f"2026-11-{offset+2:02}"
        tasks = [t for t in data['tasks'] if t['scheduled_date'] == day]
        total = sum(t['planned_minutes'] for t in tasks)
        english = sum(t['planned_minutes'] for t in tasks if t['subject'] == 'english')
        assert total == (90 if offset < 5 else 180)
        assert abs(english - total * .65) <= 1
    assert all(t['lesson_slug'] for t in data['tasks'] if t['kind'] == 'lesson')
    assert any(t['subject'] == 'python' for t in data['tasks'])


def test_settings_validation_and_zero_days(client, monkeypatch):
    freeze(monkeypatch)
    settings = client.get('/api/planner/settings').json()
    assert settings['timezone'] == 'Asia/Almaty'
    settings.pop('timezone'); settings.pop('english_percent')
    settings['available_minutes'] = [0, 60, 0, 60, 0, 120, 0]
    assert client.post('/api/planner/settings', json=settings).status_code == 200
    assert client.get('/api/planner/settings').json()['available_minutes'] == settings['available_minutes']
    assert generate(client)['planned_minutes'] == 240
    for value in [[30], [-1]*7, [True]*7, [481]*7]:
        assert client.post('/api/planner/settings', json={**settings, 'available_minutes':value}).status_code == 422


def test_completion_requires_lesson_and_is_idempotent(client, monkeypatch):
    freeze(monkeypatch)
    tasks = generate(client)['tasks']
    lesson = next(t for t in tasks if t['kind'] == 'lesson')
    assert client.post(f"/api/planner/tasks/{lesson['id']}/complete", json={'actual_minutes':15}).status_code == 409
    practice = next(t for t in tasks if t['kind'] == 'practice' and t['scheduled_date'] == '2026-11-02')
    url = f"/api/planner/tasks/{practice['id']}/complete"
    assert client.post(url, json={'actual_minutes':18}).json()['actual_minutes'] == 18
    assert client.post(url, json={'actual_minutes':99}).json()['actual_minutes'] == 18
    history = client.get('/api/planner/history').json()
    assert len(history) == 1
    assert history[0]['completed_at'].endswith('Z')
    assert client.get('/api/planner/week?start=2026-11-02').json()['completed_minutes'] == 18
    future = next(t for t in tasks if t['scheduled_date'] == '2026-11-03')
    assert client.post(f"/api/planner/tasks/{future['id']}/complete", json={'actual_minutes':20}).status_code == 409


def test_rescheduling_and_rebuild_preserve_completed_history(client, database, monkeypatch):
    freeze(monkeypatch)
    data = generate(client)
    task = next(t for t in data['tasks'] if t['kind'] == 'practice' and t['scheduled_date'] == '2026-11-02')
    # Full day cannot accept another task.
    url = f"/api/planner/tasks/{task['id']}/reschedule"
    assert client.post(url, json={'scheduled_date':'2026-11-03'}).status_code == 409
    assert client.post(url, json={'scheduled_date':'2026-11-09'}).status_code == 200
    assert client.post(url, json={'scheduled_date':'2026-11-01'}).status_code == 422
    assert client.post(url, json={'scheduled_date':'2026-11-09'}).status_code == 200
    engine = make_engine('sqlite:///' + database.as_posix())
    with Session(engine) as session:
        assert len(session.exec(select(TaskMove)).all()) == 1
    engine.dispose()
    other = next(t for t in data['tasks'] if t['id'] != task['id'] and t['kind'] == 'practice' and t['scheduled_date'] == '2026-11-02')
    client.post(f"/api/planner/tasks/{other['id']}/complete", json={'actual_minutes':12})
    response = client.post('/api/planner/generate', json={'week_start':'2026-11-02', 'replace_pending':True})
    assert response.status_code == 200, response.text
    assert len(client.get('/api/planner/history').json()) == 1
    # Moved tasks stay on the chosen day after rebuilding their original week.
    assert any(t['id'] == task['id'] for t in client.get('/api/planner/week?start=2026-11-09').json()['tasks'])


def test_overdue_and_timezone_day_boundary(client, monkeypatch):
    freeze(monkeypatch)
    generate(client)
    freeze(monkeypatch, '2026-11-02T19:01:00+00:00')
    assert clock.local_day().isoformat() == '2026-11-03'
    week = client.get('/api/planner/week').json()
    assert week['overdue']
    assert all(t['scheduled_date'] == '2026-11-02' for t in week['overdue'])
    assert client.post('/api/planner/generate', json={'week_start':'2026-10-26'}).status_code == 422
