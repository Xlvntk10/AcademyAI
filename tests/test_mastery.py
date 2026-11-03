import json
from pathlib import Path
from uuid import uuid4
from tests.test_learning import start, exercises, ANSWERS


def test_new_levels_are_structured_original_content():
    root = Path(__file__).resolve().parents[1] / 'migrations/data'
    for level in ('b1', 'b2'):
        lessons = json.loads((root/f'english-{level}-v1.json').read_text(encoding='utf8'))
        assert len(lessons) == 10
        assert len({l['slug'] for l in lessons}) == 10
        questions = []
        for lesson in lessons:
            assert len(lesson['theory']) == 4 and len(lesson['exercises']) == 6
            assert any(len(t['body']) > 200 for t in lesson['theory'])
            assert {e['kind'] for e in lesson['exercises']} == {'choice', 'text'}
            for e in lesson['exercises']:
                assert e['explanation']
                if e['kind'] == 'choice':
                    assert e['options'].count(e['correct_answer']) == 1
                questions.append(e['question'])
        assert len(set(questions)) == len(questions)


def test_unlock_is_server_enforced_and_mastery_requires_80_percent(client):
    first = next(l for l in client.get('/api/lessons').json() if l['level'] == 'B1')
    assert not first['unlocked'] and len(first['prerequisites']) == 10
    assert client.get(f"/api/lessons/{first['slug']}").status_code == 200  # Theory is previewable.
    assert client.post(f"/api/lessons/{first['slug']}/runs", json={'request_id':str(uuid4())}).status_code == 409
    for wrong_count, expected in ((2, False), (1, True), (3, True)):
        run = start(client)
        for i, (exercise, correct) in enumerate(zip(exercises(client), ANSWERS)):
            wrong = next((v for v in exercise['options'] if v != correct), 'wrong') if exercise['kind'] == 'choice' else 'wrong'
            response = client.post(f"/api/runs/{run['id']}/answers", json={'exercise_id':exercise['id'], 'answer':wrong if i < wrong_count else correct})
            assert response.status_code == 200
        saved = client.get('/api/lessons/a2-daily-routine').json()
        assert saved['mastered'] is expected
    assert saved['best_percent'] == 83.3
    assert len(client.get(f"/api/lessons/{first['slug']}").json()['prerequisites']) == 9
