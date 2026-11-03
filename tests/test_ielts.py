from datetime import datetime, timedelta
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlmodel import Session, select
from fastapi.testclient import TestClient
from app.database.db import make_engine
from app.database.models import IeltsTest
from app.main import create_app
from app.services import clock


def begin(client, test='reading-bikes'):
    response = client.post(f'/api/ielts/tests/{test}/runs', json={'request_id':str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def test_catalogue_and_public_questions_do_not_expose_keys(client):
    tests = client.get('/api/ielts/tests').json()
    assert len(tests) == 9
    assert {t['section'] for t in tests} == {'reading','listening','writing','speaking'}
    for item in tests:
        detail = client.get('/api/ielts/tests/'+item['id']).json()
        assert 'тренировочная' in detail['instructions']
        for q in detail['content'].get('questions',[]):
            assert 'answer' not in q and 'accepted' not in q and 'explanation' not in q
    assert client.get('/api/ielts/history').json() == []


@pytest.mark.parametrize('test_id', ['reading-bikes','reading-workshops','listening-course','listening-gardens'])
def test_objective_tests_grade_on_server_and_restore(client,database,monkeypatch,test_id):
    moment = datetime.fromisoformat('2026-11-04T10:00:00+00:00')
    monkeypatch.setattr(clock,'now',lambda:moment)
    run = begin(client,test_id)
    engine = make_engine('sqlite:///'+database.as_posix())
    with Session(engine) as session:
        test = session.get(IeltsTest,test_id)
        questions = test.content['questions']
        duration = test.duration_seconds
    answers = {q['id']:q['answer'] for q in questions}
    answers.pop(questions[0]['id'])  # Blank answer is incorrect, not silently omitted.
    body = {'revision':0,'answers':answers,'mode':'audio' if test_id.startswith('listening') else 'text'}
    moment += timedelta(seconds=duration+1)
    result = client.post(f"/api/ielts/runs/{run['id']}/submit",json=body)
    assert result.status_code == 200, result.text
    saved=result.json()
    assert saved['result']['score'] == len(questions)-1
    assert saved['result']['over_time']
    assert saved['result']['elapsed_seconds'] == duration+1
    assert saved['result']['answers'][0]['is_correct'] is False
    assert client.post(f"/api/ielts/runs/{run['id']}/submit",json=body).json() == saved
    assert len(client.get('/api/ielts/history').json()) == 1
    with TestClient(create_app(engine)) as restarted:
        assert restarted.get(f"/api/ielts/runs/{run['id']}").json() == saved
    stats = client.get('/api/dashboard').json()
    assert stats['total_xp'] == 0 and stats['current_streak'] == 1
    assert stats['activity'][-1]['ielts_sessions'] == 1
    engine.dispose()


def test_writing_drafts_conflicts_and_no_fake_band(client):
    run=begin(client,'writing-task1')
    url=f"/api/ielts/runs/{run['id']}"
    body={'revision':0,'text':'English increased.\n\nPhotography decreased.'}
    saved=client.post(url+'/save',json=body).json()
    assert saved['revision'] == 1
    assert client.post(url+'/save',json=body).json() == saved
    assert client.post(url+'/save',json={**body,'text':'overwrite'}).status_code == 409
    assert client.get(url).json()['text'] == body['text']
    completed=client.post(url+'/submit',json={**body,'revision':1}).json()
    assert completed['result']['score'] is None
    assert completed['result']['word_count'] == 4
    assert completed['result']['paragraphs'] == 2
    assert len(completed['result']['criteria']) == 4
    assert '150' in completed['result']['recommendations'][0]
    assert 'band' not in completed['result']
    assert client.post(url+'/save',json={**body,'revision':2}).status_code == 409


def test_concurrent_drafts_do_not_overwrite_each_other(client):
    run=begin(client,'writing-task2')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda text: client.post(f"/api/ielts/runs/{run['id']}/save",json={'revision':0,'text':text}), ['First draft','Second draft']))
    assert sorted(r.status_code for r in responses)==[200,409]


def test_invalid_fields_and_speaking_text_mode(client):
    run=begin(client,'speaking-long-turn')
    url=f"/api/ielts/runs/{run['id']}/submit"
    for extra in ({'score':9},{'band':9},{'elapsed_seconds':1},{'answers':{'unknown':'x'}}):
        assert client.post(url,json={'revision':0,'text':'My answer',**extra}).status_code==422
    assert client.post(url,json={'revision':0,'text':' '}).status_code==422
    assert client.post(url,json={'revision':0,'text':'x'*20001}).status_code==422
    result=client.post(url,json={'revision':0,'text':'I learned to repair a bicycle.'}).json()
    assert result['result']['score'] is None and result['mode']=='text'
    assert any(c['title']=='Произношение' for c in result['result']['criteria'])
