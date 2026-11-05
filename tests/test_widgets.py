def test_widgets_real_data_and_optional_countdown(client):
    initial = client.get('/api/widgets/v1/summary')
    assert initial.headers['cache-control'] == 'no-store'
    data = initial.json()
    assert data['schema_version'] == 1
    assert data['streak']['current'] == 0
    assert data['today_tasks'] == []
    assert data['masters_countdown']['days_remaining'] is None
    assert [s['available_lessons'] for s in data['subjects']] == [30, 10]
    assert all(s['mastered_lessons'] == 0 for s in data['subjects'])
    settings = client.get('/api/planner/settings').json()
    settings.pop('timezone')
    settings['masters_target_date'] = '2028-09-01'
    assert client.post('/api/planner/settings', json=settings).status_code == 200
    countdown = client.get('/api/widgets/v1/summary').json()['masters_countdown']
    assert countdown['target_date'] == '2028-09-01' and countdown['days_remaining'] > 0


def test_reminder_days_validate_and_preserve_other_settings(client):
    original = client.get('/api/planner/settings').json()
    response = client.post('/api/planner/reminder', json=dict(reminder_enabled=True, reminder_time='20:15', reminder_days=[0,2,2,5]))
    assert response.status_code == 200
    assert response.json()['reminder_days'] == [0,2,5]
    assert response.json()['available_minutes'] == original['available_minutes']
    assert client.post('/api/planner/reminder', json=dict(reminder_enabled=True, reminder_time='20:15', reminder_days=[7])).status_code == 422
    legacy = client.post('/api/planner/reminder', json=dict(reminder_enabled=False, reminder_time='20:15'))
    assert legacy.json()['reminder_days'] == [0,2,5]
