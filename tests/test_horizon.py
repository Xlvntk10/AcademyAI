from datetime import datetime
import sqlite3
from app.services import clock
from scripts.prepare_db import snapshot
from tests.test_planner import freeze, generate
from tests.test_learning import start, exercises


def settings_payload(client, **changes):
    data=client.get('/api/planner/settings').json()
    data.pop('timezone')
    return {**data,**changes}


def test_horizon_is_empty_until_target_is_chosen_and_calendar_handles_leap_year(client,monkeypatch):
    freeze(monkeypatch)
    empty=client.get('/api/planner/roadmap').json()
    assert empty['target_month'] is None and empty['months']==[]
    assert empty['mastered_count']==0 and empty['total_topics']==40
    assert all(t['status']=='locked' for t in empty['topics'] if t['level'] in ('B1','B2'))
    prefs=settings_payload(client,target_month='2028-02',available_minutes=[10]*7,english_percent=80,monthly_goal_minutes=200)
    assert client.post('/api/planner/settings',json=prefs).status_code==200
    plan=client.get('/api/planner/roadmap').json()
    assert len(plan['months'])==16
    leap=plan['months'][-1]
    assert leap['month']=='2028-02'
    assert leap['available_minutes']==290
    assert leap['english_minutes']==232 and leap['python_minutes']==58
    assert plan['monthly_goal']['completed_minutes']==0
    week=generate(client)
    monday=[t for t in week['tasks'] if t['scheduled_date']=='2026-11-02']
    assert sum(t['planned_minutes'] for t in monday if t['subject']=='english')==8


def test_target_and_proportion_validation(client,monkeypatch):
    freeze(monkeypatch)
    for change in ({'target_month':'2026-10'},{'target_month':'2029-01'},{'target_month':'2028-13'}, {'english_percent':101},{'english_percent':True},{'monthly_goal_minutes':0}):
        assert client.post('/api/planner/settings',json=settings_payload(client,**change)).status_code==422
    assert client.post('/api/planner/settings',json=settings_payload(client,english_percent=0)).status_code==200
    assert all(t['subject']=='python' for t in generate(client)['tasks'])


def test_adaptation_preserves_completions_moves_and_capacity(client,database,monkeypatch):
    freeze(monkeypatch)
    week=generate(client)
    done=next(t for t in week['tasks'] if t['kind']=='practice' and t['scheduled_date']=='2026-11-02')
    assert client.post(f"/api/planner/tasks/{done['id']}/complete",json={'actual_minutes':18}).status_code==200
    moved=next(t for t in week['tasks'] if t['scheduled_date']=='2026-11-03')
    assert client.post(f"/api/planner/tasks/{moved['id']}/reschedule",json={'scheduled_date':'2026-11-09'}).status_code==200
    freeze(monkeypatch,'2026-11-05T07:00:00+00:00')
    response=client.post('/api/planner/adapt',json={'week_start':'2026-11-02'})
    assert response.status_code==200,response.text
    data=response.json()
    assert data['moved']>0 and data['remaining_overdue']==0
    tasks=data['week']['tasks']
    assert next(t for t in tasks if t['id']==done['id'])['actual_minutes']==18
    future=client.get('/api/planner/week?start=2026-11-09').json()
    assert any(t['id']==moved['id'] for t in future['tasks'])
    for day in ('2026-11-05','2026-11-06','2026-11-07','2026-11-08'):
        limit=180 if day in ('2026-11-07','2026-11-08') else 90
        assert sum(t['planned_minutes'] for t in tasks if t['scheduled_date']==day)<=limit
    before=snapshot(database)
    assert client.post('/api/planner/adapt',json={'week_start':'2026-11-02'}).json()['moved']==0
    assert snapshot(database)==before
    assert client.get('/api/planner/roadmap').json()['monthly_goal']['completed_minutes']==18


def test_no_room_retains_overdue_and_never_marks_it_complete(client,monkeypatch):
    freeze(monkeypatch)
    generate(client)
    freeze(monkeypatch,'2026-11-09T07:00:00+00:00')
    assert client.post('/api/planner/settings',json=settings_payload(client,available_minutes=[0]*7)).status_code==200
    data=client.post('/api/planner/adapt',json={'week_start':'2026-11-09'}).json()
    assert data['moved']==0 and data['remaining_overdue']>0
    assert client.get('/api/planner/history').json()==[]


def test_zero_score_recommends_review_instead_of_claiming_mastery(client):
    run=start(client)
    for q in exercises(client):
        client.post(f"/api/runs/{run['id']}/answers",json={'exercise_id':q['id'],'answer':q['options'][0] if q['options'] else 'wrong'})
    roadmap=client.get('/api/planner/roadmap').json()
    recommendation=next(r for r in roadmap['recommendations'] if r['route']=='lesson/a2-daily-routine')
    assert 'Лучший результат' in recommendation['reason']


def test_adaptation_keeps_future_manual_moves_and_started_lessons(client,monkeypatch):
    from uuid import uuid4
    freeze(monkeypatch)
    week=generate(client)
    client.post('/api/planner/settings',json=settings_payload(client,available_minutes=[240]*7))
    task=next(t for t in week['tasks'] if t['kind']=='practice' and t['scheduled_date']=='2026-11-03')
    assert client.post(f"/api/planner/tasks/{task['id']}/reschedule",json={'scheduled_date':'2026-11-06'}).status_code==200
    lesson=next(t for t in week['tasks'] if t['kind']=='lesson' and t['scheduled_date']=='2026-11-06')
    assert client.post(f"/api/lessons/{lesson['lesson_slug']}/runs",json={'request_id':str(uuid4())}).status_code==200
    freeze(monkeypatch,'2026-11-05T07:00:00+00:00')
    response=client.post('/api/planner/adapt',json={'week_start':'2026-11-02'})
    assert response.status_code==200,response.text
    tasks={t['id']:t for t in response.json()['week']['tasks']}
    for saved in (task,lesson):
        assert tasks[saved['id']]['scheduled_date']=='2026-11-06'
        assert tasks[saved['id']]['status']=='pending'
