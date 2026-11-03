def test_reminder_settings_persist_without_overwriting_planner(client):
    before = client.get('/api/planner/settings').json()
    result = client.post('/api/planner/reminder', json={'reminder_enabled':True,'reminder_time':'20:45'})
    assert result.status_code == 200
    after = client.get('/api/planner/settings').json()
    assert after['reminder_time'] == '20:45'
    assert after['reminder_enabled']
    assert after['available_minutes'] == before['available_minutes']
    assert after['daily_goal_minutes'] == before['daily_goal_minutes']
    for time in ['25:00','9:00','19:75','tomorrow']:
        assert client.post('/api/planner/reminder',json={'reminder_enabled':True,'reminder_time':time}).status_code == 422
