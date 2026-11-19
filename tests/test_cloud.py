"""Real PostgreSQL integration tests. Both URLs must point to a dedicated *_test DB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from datetime import datetime
from pathlib import Path
import os
import sqlite3
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.accounts import AccountConfig, SupabaseAuth, COOKIE
from app.cloud_accounts import CloudAccounts
from app.database.cloud import read_profile, copy_profile, set_owner
from app.database.db import make_engine
from app.main import create_app
from scripts.import_cloud import import_cloud
from scripts.migrate_cloud import migrate_cloud
from scripts.prepare_db import snapshot
from tests import test_accounts as local
from tests.test_offline import submission


@pytest.fixture
def cloud_engines():
    runtime_url = os.environ.get("ACADEMY_TEST_DATABASE_URL")
    admin_url = os.environ.get("ACADEMY_TEST_ADMIN_URL")
    if not runtime_url or not admin_url:
        pytest.skip("Dedicated PostgreSQL test URLs were not supplied")
    for url in (runtime_url, admin_url):
        if not sa.engine.make_url(url).database.endswith("_test"):
            pytest.fail("Refusing PostgreSQL tests outside a dedicated *_test database")
    migrate_cloud(admin_url)
    runtime, admin = make_engine(runtime_url), make_engine(admin_url)
    with admin.begin() as connection:
        connection.execute(sa.text("DELETE FROM academy_auth.auth_limits"))
    yield runtime, admin
    runtime.dispose()
    admin.dispose()


@pytest.fixture
def cloud_app(cloud_engines, monkeypatch):
    runtime, _ = cloud_engines
    monkeypatch.setattr(local, "USERS", {email: str(uuid4()) for email in local.USERS})
    boundary = local.AuthHTTP()
    config = AccountConfig(local.ORIGIN, "https://project.supabase.co", "sb_publishable_test", None)
    manager = CloudAccounts(config, runtime, SupabaseAuth(config, httpx.MockTransport(boundary)))
    app = create_app(runtime, accounts=manager)
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(app, base_url=local.ORIGIN, headers={
            "Origin": local.ORIGIN, "X-Academy-Request": "1"})) for _ in range(3)]
        yield app, manager, boundary, clients


def test_two_devices_offline_retry_xp_streak_plan(cloud_app, database):
    _, _, _, (desktop, phone, other) = cloud_app
    before = snapshot(database)
    local.login(desktop)
    local.login(phone)
    local.login(other, "two@example.test")
    # Device A retains a complete offline submission across a network outage.
    payload = submission(desktop)
    assert phone.get('/api/progress').json()['total_xp'] == 0
    first = desktop.post('/api/offline/attempts', json=payload)
    assert first.status_code == 200, first.text
    with ThreadPoolExecutor(max_workers=2) as pool:
        retries = list(pool.map(lambda c: c.post('/api/offline/attempts', json=payload), [desktop, phone]))
    assert all(r.json() == first.json() for r in retries)
    a, b = [c.get('/api/sync/snapshot').json() for c in (desktop, phone)]
    assert a['progress'] == b['progress']
    assert b['progress']['total_xp'] == 60
    assert b['dashboard']['current_streak'] == 1
    assert other.get('/api/progress').json()['total_xp'] == 0
    assert other.get('/api/runs/' + payload['attempt_id']).status_code == 404
    assert other.post('/api/offline/attempts', json=payload).status_code == 409
    own = submission(other)
    own['attempt_id'] = payload['attempt_id']
    assert other.post('/api/offline/attempts', json=own).status_code == 200
    assert other.get('/api/progress', headers={'X-Academy-Account': local.USERS['one@example.test']}).status_code == 409
    week = desktop.get('/api/planner/week').json()
    response = desktop.post('/api/planner/generate', json={'week_start':week['week_start']}, headers={'If-Match':week['sync_revision']})
    assert response.status_code == 200, response.text
    assert phone.get('/api/planner/week').json() == response.json()
    assert other.get('/api/planner/week').json()['tasks'] == []
    assert snapshot(database) == before


def test_cloud_plan_conflicts(cloud_app):
    local.test_planner_conflict_preserves_newer_settings(cloud_app)


def test_cloud_private_modules(cloud_app):
    local.test_private_modules_and_ielts_are_account_scoped(cloud_app)


def test_cloud_identity_and_limits(cloud_app):
    local.test_provider_identity_validation_and_request_limits(cloud_app)


def test_sessions_restart_refresh_outage_expiry_logout(cloud_app, cloud_engines):
    app, manager, boundary, (desktop, phone, _) = cloud_app
    runtime, admin = cloud_engines
    local.login(desktop)
    local.login(phone)
    cookie = desktop.cookies.get(COOKIE)
    restarted = CloudAccounts(manager.config, runtime, manager.provider)
    assert restarted.resolve(cookie)['id'] == local.USERS['one@example.test']
    with admin.begin() as connection:
        connection.execute(sa.text('UPDATE academy_auth.sessions SET token_expires=0 WHERE digest=:digest'), {'digest':manager.digest(cookie)})
    with ThreadPoolExecutor(max_workers=3) as pool:
        identities = list(pool.map(restarted.resolve, [cookie]*3))
    assert len({identity['id'] for identity in identities}) == 1
    assert boundary.refresh_count == 1
    boundary.offline = True
    assert desktop.get('/api/progress').status_code == 503
    boundary.offline = False
    assert desktop.get('/api/progress').status_code == 200
    assert desktop.post('/api/auth/logout', json={}).status_code == 200
    desktop.cookies.set(COOKIE, cookie)
    assert desktop.get('/api/progress').status_code == 401
    assert phone.get('/api/progress').status_code == 200
    with admin.begin() as connection:
        connection.execute(sa.text('UPDATE academy_auth.sessions SET session_expires=0 WHERE user_id=:id'), {'id':local.USERS['one@example.test']})
    assert phone.get('/api/progress').status_code == 401


def test_row_security_and_pool_context(cloud_app, cloud_engines):
    _, manager, _, (first, second, _) = cloud_app
    local.login(first)
    local.login(second, 'two@example.test')
    runtime, admin = cloud_engines
    owner, other = local.USERS.values()
    with runtime.begin() as connection:
        assert connection.execute(sa.text('SELECT count(*) FROM academy.lesson')).scalar_one() == 0
        set_owner(connection, owner)
        assert connection.execute(sa.text('SELECT DISTINCT user_id FROM academy.lesson')).scalars().all() == [owner]
    with runtime.begin() as connection:
        assert connection.execute(sa.text('SELECT count(*) FROM academy.lesson')).scalar_one() == 0
        set_owner(connection, other)
        assert connection.execute(sa.text('SELECT DISTINCT user_id FROM academy.lesson')).scalars().all() == [other]
    with pytest.raises(sa.exc.DBAPIError), runtime.begin() as connection:
        set_owner(connection, owner)
        connection.execute(sa.text("INSERT INTO academy.syncidentity(user_id,id,server_id) VALUES (:other,2,'forbidden')"), {'other':other})
    with pytest.raises(RuntimeError, match='NOBYPASSRLS'):
        CloudAccounts(manager.config, admin, manager.provider)


def test_cors_and_csrf(cloud_app):
    _, _, _, (client, _, _) = cloud_app
    request = {'Origin':local.ORIGIN, 'Access-Control-Request-Method':'POST', 'Access-Control-Request-Headers':'X-Academy-Account,If-Match,X-Academy-Request'}
    allowed = client.options('/api/offline/attempts', headers=request)
    assert allowed.status_code == 200
    assert allowed.headers['access-control-allow-origin'] == local.ORIGIN
    denied = client.options('/api/offline/attempts', headers={**request,'Origin':'https://evil.test'})
    assert denied.status_code == 400
    assert 'access-control-allow-origin' not in denied.headers
    assert client.post('/api/auth/code',json={'email':'one@example.test'},headers={'Origin':'https://evil.test'}).status_code == 403


def test_import_preserves_rows_retries_and_demo_separation(cloud_app, cloud_engines, database, tmp_path):
    _, _, _, (desktop, phone, other) = cloud_app
    engine = make_engine('sqlite:///' + database.as_posix())
    with TestClient(create_app(engine)) as legacy:
        payload = submission(legacy)
        original_result = legacy.post('/api/offline/attempts',json=payload)
        assert original_result.status_code == 200
    engine.dispose()
    with closing(sqlite3.connect(database)) as db:
        exercise = db.execute('SELECT id FROM exercise LIMIT 1').fetchone()[0]
        db.execute("INSERT INTO attempt(exercise_id,answer,is_correct,earned_points,created_at) VALUES (?, 'demo', 1, 1000, '2026-11-05 10:00:00')",(exercise,))
        db.commit()
    before = snapshot(database)
    url = os.environ['ACADEMY_TEST_ADMIN_URL']
    for owner in local.USERS.values():
        saved = import_cloud(database, owner, url, tmp_path/'backups')
        assert snapshot(saved) == before == snapshot(database)
        with pytest.raises(ValueError, match='already exists'):
            import_cloud(database, owner, url, tmp_path/'backups')
    local.login(desktop)
    local.login(phone)
    local.login(other, 'two@example.test')
    for client in (desktop,phone,other):
        assert client.get('/api/progress').json()['total_xp'] == 60
        assert client.post('/api/offline/attempts',json=payload).json() == original_result.json()
    new_payload = submission(desktop)
    new_payload['attempt_id'] = str(uuid4())
    response = desktop.post('/api/offline/attempts',json=new_payload)
    assert response.status_code == 200, response.text
    assert snapshot(database) == before


def test_failed_copy_rolls_back_every_table(cloud_engines, database):
    _, admin = cloud_engines
    owner = str(uuid4())
    profile = read_profile(database)
    profile['attempt'] = [{'id':999, 'exercise_id':99999999, 'answer':'bad', 'is_correct':False, 'earned_points':0, 'created_at':datetime.now()}]
    with pytest.raises(sa.exc.IntegrityError), admin.begin() as connection:
        connection.execute(sa.text('INSERT INTO academy_auth.users(user_id) VALUES (:id)'),{'id':owner})
        copy_profile(connection,owner,profile)
    with admin.connect() as connection:
        assert connection.execute(sa.text('SELECT count(*) FROM academy_auth.users WHERE user_id=:id'),{'id':owner}).scalar_one() == 0
        assert connection.execute(sa.text('SELECT count(*) FROM academy.lesson WHERE user_id=:id'),{'id':owner}).scalar_one() == 0


@pytest.mark.parametrize('scenario', ['writing', 'concurrent_writing', 'speaking', 'vocabulary'])
def test_existing_learning_modules_on_postgresql(cloud_app, monkeypatch, scenario):
    from tests import test_ielts, test_vocabulary
    client = cloud_app[3][0]
    local.login(client)
    if scenario == 'writing':
        test_ielts.test_writing_drafts_conflicts_and_no_fake_band(client)
    elif scenario == 'concurrent_writing':
        test_ielts.test_concurrent_drafts_do_not_overwrite_each_other(client)
    elif scenario == 'speaking':
        test_ielts.test_invalid_fields_and_speaking_text_mode(client)
    else:
        test_vocabulary.test_spaced_intervals_reset_after_error_and_reviews_count_for_streak(client, monkeypatch)


def test_all_existing_courses_on_postgresql(cloud_app, database):
    from tests.test_curriculum import test_all_forty_lessons_complete_and_award_only_real_results
    client = cloud_app[3][0]
    local.login(client)
    test_all_forty_lessons_complete_and_award_only_real_results(client, database)


def test_backup_and_restore_into_separate_database(cloud_engines, tmp_path):
    from scripts.cloud_backup import backup_cloud, restore_cloud
    bin_path = os.environ.get('ACADEMY_TEST_PG_BIN')
    if not bin_path:
        pytest.skip('PostgreSQL client binaries are required for backup/restore rehearsal')
    _, admin = cloud_engines
    # Database creation requires a disposable local cluster administrator.
    name = 'academy_restore_' + uuid4().hex + '_test'
    with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql('CREATE DATABASE ' + name)
    restored = make_engine(admin.url.set(database=name).render_as_string(hide_password=False))
    archive = tmp_path/'verified.dump'
    url = os.environ['ACADEMY_TEST_ADMIN_URL']
    backup_cloud(url, archive, Path(bin_path))
    restore_cloud(restored.url.render_as_string(hide_password=False), archive, Path(bin_path))
    try:
        with admin.connect() as source, restored.connect() as destination:
            for schema in ('academy', 'academy_auth', 'academy_migrations'):
                metadata = sa.MetaData(schema=schema)
                metadata.reflect(source, schema=schema)
                for table in metadata.sorted_tables:
                    if table.schema != schema:
                        continue
                    expected = source.execute(table.select()).fetchall()
                    actual = destination.execute(table.select()).fetchall()
                    assert sorted(expected, key=repr) == sorted(actual, key=repr), table.fullname
        with pytest.raises(ValueError, match='separate empty database'):
            restore_cloud(url, archive, Path(bin_path))
    finally:
        restored.dispose()
    # Keep the restored test database for inspection. No DROP is needed.


def test_magic_link_postgresql_devices_and_isolation(cloud_app):
    from tests.test_magic_link import install, request_link
    _, manager, _, (desktop, phone, other) = cloud_app
    provider = install(manager)
    for client, email in [(desktop, 'one@example.test'), (phone, 'one@example.test'), (other, 'two@example.test')]:
        code = request_link(client, provider, email)
        result = client.post('/api/auth/exchange', json={'code': code})
        assert result.status_code == 200
        client.headers['X-Academy-Account'] = result.json()['user']['id']
    payload = submission(desktop)
    assert desktop.post('/api/offline/attempts', json=payload).status_code == 200
    assert phone.get('/api/progress').json()['total_xp'] == 60
    assert phone.post('/api/offline/attempts', json=payload).status_code == 200
    assert desktop.get('/api/progress').json()['total_xp'] == 60
    assert other.get('/api/progress').json()['total_xp'] == 0
    assert other.get('/api/runs/' + payload['attempt_id']).status_code == 404
    assert desktop.post('/api/auth/logout', json={}).status_code == 200
    assert desktop.get('/api/progress').status_code == 401
    assert phone.get('/api/progress').status_code == 200


def test_import_synthetic_40_xp_vocabulary_plan_settings_and_receipt(cloud_app, database, tmp_path):
    """A fixture with 40 XP, never the user's real SQLite or Supabase account."""
    _, _, _, (desktop, phone, outsider) = cloud_app
    engine = make_engine('sqlite:///' + database.as_posix())
    with TestClient(create_app(engine)) as source:
        payload = submission(source)
        payload['answers'][0]['answer'] = 'study'
        payload['answers'][1]['answer'] = "don't drink"
        accepted = source.post('/api/offline/attempts', json=payload)
        assert accepted.status_code == 200
        assert source.get('/api/progress').json()['total_xp'] == 40
        word = next(w for w in source.get('/api/vocabulary').json()['words'] if w['unlocked'])
        assert source.post(f"/api/vocabulary/{word['id']}/add").status_code == 200
        review = {'request_id':str(uuid4()), 'answer':word['term']}
        assert source.post(f"/api/vocabulary/{word['id']}/review", json=review).status_code == 200
        prefs = source.get('/api/planner/settings').json()
        prefs.pop('timezone'); prefs.pop('english_percent')
        prefs['available_minutes'] = [30, 45, 60, 30, 45, 90, 60]
        assert source.post('/api/planner/settings', json=prefs).status_code == 200
        week = source.get('/api/planner/week').json()
        assert source.post('/api/planner/generate', json={'week_start':week['week_start']}).status_code == 200
        routes = ['/api/progress', '/api/dashboard', '/api/vocabulary', '/api/planner/settings', '/api/planner/week']
        expected = {route:source.get(route).json() for route in routes}
    engine.dispose()
    before = snapshot(database)
    saved = import_cloud(database, local.USERS['one@example.test'], os.environ['ACADEMY_TEST_ADMIN_URL'], tmp_path/'saved')
    assert snapshot(saved) == before == snapshot(database)
    local.login(desktop); local.login(phone); local.login(outsider, 'two@example.test')
    def without_revision(value):
        if isinstance(value, dict):
            return {k:without_revision(v) for k,v in value.items() if k != 'sync_revision'}
        if isinstance(value, list):
            return [without_revision(v) for v in value]
        return value
    # Authenticated sync adds revision tokens; stored settings themselves must match.
    for client in (desktop, phone):
        for route, value in expected.items():
            assert without_revision(client.get(route).json()) == without_revision(value), route
        assert client.get('/api/planner/settings').json()['sync_revision']
        assert client.post('/api/offline/attempts', json=payload).json() == accepted.json()
        assert client.get('/api/progress').json()['total_xp'] == 40
    assert outsider.get('/api/progress').json()['total_xp'] == 0
    assert outsider.get('/api/runs/' + payload['attempt_id']).status_code == 404
    assert snapshot(database) == before


def test_production_accepts_verified_tls_runtime(cloud_app, cloud_engines, monkeypatch):
    _, manager, _, _ = cloud_app
    runtime, _ = cloud_engines
    assert runtime.url.query['sslmode'] == 'verify-full'
    monkeypatch.setenv('ACADEMY_ENV', 'production')
    with TestClient(create_app(runtime, accounts=manager)) as client:
        assert client.get('/api/health').status_code == 200
