from datetime import date, datetime, timedelta
from app.services import clock
from app.services.analytics import streaks
from tests.test_learning import start, exercises, ANSWERS


def test_streak_calendar_boundaries_and_gaps():
    today = date(2026, 11, 9)
    days = [today-timedelta(days=i) for i in range(7)]
    assert streaks(days, today) == (7, 7, today)
    assert streaks(days, today+timedelta(days=1))[:2] == (7, 7)
    assert streaks(days, today+timedelta(days=2))[:2] == (0, 7)
    assert streaks([today, today-timedelta(days=2)], today)[:2] == (1, 1)
    assert streaks([], today)[:2] == (0, 0)


def test_dashboard_empty_and_first_real_lesson(client, monkeypatch):
    monkeypatch.setattr(clock, 'now', lambda: datetime.fromisoformat('2026-11-02T19:01:00+00:00'))
    empty = client.get('/api/dashboard').json()
    assert empty['today'] == '2026-11-03'
    assert empty['accuracy'] is None
    assert empty['current_streak'] == empty['total_xp'] == 0
    assert all(a['unlocked_on'] is None for a in empty['achievements'])
    run = start(client)
    for item, answer in zip(exercises(client), ANSWERS):
        client.post(f"/api/runs/{run['id']}/answers", json={'exercise_id':item['id'], 'answer':answer})
    data = client.get('/api/dashboard').json()
    assert data['total_xp'] == 60
    assert data['answers'] == data['correct_answers'] == 6
    assert data['current_streak'] == 1
    assert data['accuracy'] == 100
    assert data['minutes'] == 0  # No fabricated time from planned lesson duration.
    assert next(a for a in data['achievements'] if a['code'] == 'first_step')['unlocked_on'] == '2026-11-03'
    assert data == client.get('/api/dashboard').json()


def test_practice_xp_daily_cap_and_recorded_minutes(client, monkeypatch):
    monkeypatch.setattr(clock, 'now', lambda: datetime.fromisoformat('2026-11-02T07:00:00+00:00'))
    week = client.post('/api/planner/generate', json={'week_start':'2026-11-02'}).json()
    tasks = [t for t in week['tasks'] if t['scheduled_date'] == '2026-11-02' and t['kind'] == 'practice']
    for task in tasks:
        client.post(f"/api/planner/tasks/{task['id']}/complete", json={'actual_minutes':10})
        client.post(f"/api/planner/tasks/{task['id']}/complete", json={'actual_minutes':10})
    data = client.get('/api/dashboard').json()
    assert data['practice_xp'] == 20
    assert data['minutes'] == 10*len(tasks)
    assert data['daily_goal']['reached']
    assert data['current_streak'] == 1
    assert client.get('/api/progress').json()['total_xp'] == data['total_xp']
    assert data['weekly_report']['minutes'] == data['minutes']
