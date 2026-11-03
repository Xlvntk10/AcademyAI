import ast
import json
from pathlib import Path
from uuid import uuid4
from sqlmodel import Session, select
from app.database.db import make_engine
from app.database.models import Exercise, ExerciseContent


def test_authored_content_has_valid_examples_and_unambiguous_keys():
    root = Path(__file__).resolve().parents[1] / 'migrations/data'
    lessons = json.loads((root/'english-a2-v1.json').read_text(encoding='utf-8')) + json.loads((root/'python-basics-v1.json').read_text(encoding='utf-8'))
    assert len(lessons) == 19
    assert len({l['slug'] for l in lessons}) == 19
    for lesson in lessons:
        assert '???' not in json.dumps(lesson, ensure_ascii=False)
        assert any('а' <= character.lower() <= 'я' for character in lesson['summary'])
        assert len(lesson['theory']) >= 4
        assert len(lesson['exercises']) == 6
        for block in lesson['theory']:
            assert len(block['body']) > 60
            if block.get('code'):
                ast.parse(block['code'])  # Parse trusted examples; never execute them.
        for exercise in lesson['exercises']:
            assert exercise['explanation']
            if exercise['kind'] == 'choice':
                assert exercise['options'].count(exercise['correct_answer']) == 1
                assert len(set(exercise['options'])) == len(exercise['options'])


def test_all_forty_lessons_complete_and_award_only_real_results(client, database):
    catalogue = client.get('/api/lessons').json()
    assert sum(l['subject'] == 'english' for l in catalogue) == 30
    assert sum(l['subject'] == 'python' for l in catalogue) == 10
    engine = make_engine('sqlite:///' + database.as_posix())
    with Session(engine) as session:
        keys = {e.id: e.correct_answer for e in session.exec(select(Exercise)).all()}
    engine.dispose()
    for lesson in catalogue:
        detail = client.get('/api/lessons/'+lesson['slug']).json()
        run = client.post('/api/lessons/'+lesson['slug']+'/runs', json={'request_id':str(uuid4())}).json()
        for exercise in detail['exercises']:
            response = client.post('/api/runs/'+run['id']+'/answers', json={'exercise_id':exercise['id'], 'answer':keys[exercise['id']]})
            assert response.status_code == 200, response.text
        assert response.json()['score'] == 60
        assert response.json()['completed_at']
    dashboard = client.get('/api/dashboard').json()
    assert dashboard['completed_lessons'] == 40
    assert dashboard['total_xp'] == 2400
    assert dashboard['answers'] == 240
    assert dashboard['level'] == 25
    awards = {a['code']: a for a in dashboard['achievements']}
    assert awards['english_explorer']['unlocked_on']
    assert awards['python_beginner']['unlocked_on']


def test_python_grading_preserves_case(client):
    lesson = client.get('/api/lessons/python-data-types').json()
    question = next(e for e in lesson['exercises'] if 'логическую истину' in e['question'])
    run = client.post('/api/lessons/python-data-types/runs', json={'request_id':str(uuid4())}).json()
    result = client.post('/api/runs/'+run['id']+'/answers', json={'exercise_id':question['id'],'answer':'true'}).json()
    assert result['answers'][0]['is_correct'] is False
    assert result['answers'][0]['earned_points'] == 0
    assert result['answers'][0]['correct_answer'] == 'True'


def test_seven_real_days_and_restart_restore_stats(client, database, monkeypatch):
    from datetime import datetime, timedelta
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.services import clock
    first = datetime.fromisoformat('2026-11-02T07:00:00+00:00')
    monkeypatch.setattr(clock, 'now', lambda: first)
    week = client.post('/api/planner/generate', json={'week_start':'2026-11-02'}).json()
    for i in range(7):
        moment = first+timedelta(days=i)
        monkeypatch.setattr(clock, 'now', lambda value=moment: value)
        task = next(t for t in week['tasks'] if t['kind'] == 'practice' and t['subject'] == 'english' and t['scheduled_date'] == clock.local_day().isoformat())
        assert client.post(f"/api/planner/tasks/{task['id']}/complete", json={'actual_minutes':30}).status_code == 200
    before = client.get('/api/dashboard').json()
    assert before['current_streak'] == 7
    assert before['weekly_goal']['reached']
    assert before['total_xp'] == 70
    assert next(a for a in before['achievements'] if a['code']=='seven_days')['unlocked_on'] == '2026-11-08'
    engine = make_engine('sqlite:///' + database.as_posix())
    with TestClient(create_app(engine)) as restarted:
        assert restarted.get('/api/dashboard').json() == before
    engine.dispose()
