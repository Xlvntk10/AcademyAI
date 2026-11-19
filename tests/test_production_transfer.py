import hashlib
import json
import os
import sqlite3
from uuid import uuid4
import pytest
import sqlalchemy as sa
from app.database.cloud import read_profile
from app.database.db import make_engine
from scripts import production_transfer as transfer
from scripts.prepare_db import backup
from tests.test_offline import submission


@pytest.fixture
def prepared(client, database, tmp_path):
    payload = submission(client)
    payload['answers'][0]['answer'] = 'study'
    payload['answers'][1]['answer'] = "don't drink"
    assert client.post('/api/offline/attempts', json=payload).status_code == 200
    assert client.get('/api/progress').json()['total_xp'] == 40
    saved = tmp_path/'copy.db'
    backup(database, saved)
    return {'source':database, 'saved':saved, 'fingerprint':transfer.source_fingerprint(database),
            'user_id':str(uuid4()), 'email':'synthetic@example.test',
            'realm':hashlib.sha256(b'https://testref.supabase.co').hexdigest()[:16],
            'profile':read_profile(saved), 'folder':tmp_path}


def local_admin():
    raw = os.environ.get('ACADEMY_TEST_ADMIN_URL')
    if not raw:
        pytest.skip('Dedicated local PostgreSQL required')
    parsed = sa.engine.make_url(raw)
    if parsed.host not in ('127.0.0.1','localhost') or not parsed.database.endswith('_test'):
        pytest.fail('Only loopback *_test database allowed')
    return parsed


def make_auth(connection, prepared):
    connection.exec_driver_sql('CREATE SCHEMA auth')
    connection.exec_driver_sql('CREATE TABLE auth.users(id uuid PRIMARY KEY, email text, email_confirmed_at timestamptz)')
    connection.execute(sa.text('INSERT INTO auth.users VALUES(CAST(:id AS uuid),:email,now())'),
                       {'id':prepared['user_id'], 'email':prepared['email']})


@pytest.fixture
def empty_destination(prepared):
    engine = make_engine(local_admin().render_as_string(hide_password=False))
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # Rename only inside an isolated local transaction; finally rolls back.
            for schema in transfer.SCHEMAS:
                connection.exec_driver_sql(f'ALTER SCHEMA {schema} RENAME TO {schema}_saved_test')
            make_auth(connection, prepared)
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def test_atomic_import_all_values_and_40_xp(empty_destination, prepared):
    result = transfer.apply_and_import(empty_destination, prepared, transfer.reviewed_plan())
    assert result['total_xp'] == 40 and result['tables_compared'] == 21
    assert result['force_rls_tables'] == 21
    assert result['outside_catalog_unchanged'] and not result['role_grants_changed']
    assert result['sessions_imported'] is False
    assert transfer.verify_import(empty_destination, prepared)['all_typed_values_match']
    transfer.assert_source_unchanged(prepared)
    with pytest.raises(transfer.TransferFailure, match='PRODUCTION_SCHEMAS_EXIST_NO_OVERWRITE'):
        transfer.apply_and_import(empty_destination, prepared, transfer.reviewed_plan())


def test_failure_rolls_back_schema_and_owner(empty_destination, prepared, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(transfer, 'copy_profile', fail)
    with pytest.raises(RuntimeError, match='synthetic failure'), empty_destination.begin_nested():
        transfer.apply_and_import(empty_destination, prepared, transfer.reviewed_plan())
    assert empty_destination.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname IN ('academy','academy_auth','academy_migrations')").scalar_one() == 0
    assert empty_destination.exec_driver_sql('SELECT count(*) FROM auth.users').scalar_one() == 1


def test_source_change_prevents_commit(empty_destination, prepared, monkeypatch):
    real = transfer.verify_import
    def change_source(connection, values):
        result = real(connection, values)
        with sqlite3.connect(values['source']) as local:
            local.execute('UPDATE studysettings SET daily_goal_minutes=daily_goal_minutes+1')
        return result
    monkeypatch.setattr(transfer, 'verify_import', change_source)
    with pytest.raises(transfer.TransferFailure, match='LOCAL_PROFILE_CHANGED'), empty_destination.begin_nested():
        transfer.apply_and_import(empty_destination, prepared, transfer.reviewed_plan())
    assert empty_destination.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname='academy'").scalar_one() == 0


def test_wrong_account_stops_before_ddl(empty_destination, prepared):
    wrong = {**prepared,'email':'other@example.test'}
    with pytest.raises(transfer.TransferFailure, match='SUPABASE_CONFIRMED_ACCOUNT_MISMATCH'):
        transfer.apply_and_import(empty_destination, wrong, transfer.reviewed_plan())
    assert empty_destination.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname='academy'").scalar_one() == 0


@pytest.mark.parametrize('grant', ['GRANT USAGE ON SCHEMA academy TO PUBLIC',
                                  'GRANT SELECT ON academy.skill TO PUBLIC'])
def test_unexpected_schema_or_table_access_refused(empty_destination, prepared, grant):
    transfer.apply_and_import(empty_destination, prepared, transfer.reviewed_plan())
    empty_destination.exec_driver_sql(grant)
    with pytest.raises(transfer.TransferFailure, match='UNEXPECTED_PRODUCTION_ACCESS_GRANT'):
        transfer.verify_import(empty_destination, prepared)


def test_project_binding():
    url = sa.engine.URL.create('postgresql', username='postgres.testref', host='test.pooler.supabase.com')
    realm = hashlib.sha256(b'https://testref.supabase.co').hexdigest()[:16]
    transfer.validate_project(url, realm)
    with pytest.raises(transfer.TransferFailure, match='PROJECT_DOES_NOT_MATCH'):
        transfer.validate_project(url, 'wrong')


def test_changed_plan_stops_before_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(transfer, 'ROOT', tmp_path)
    monkeypatch.setattr(transfer, 'render_cloud_sql', lambda: 'altered')
    monkeypatch.setattr(transfer, 'prepare_snapshot', lambda: pytest.fail('No backup or connection for modified plan'))
    result = transfer.execute('unused', ('private-uri','SECRET'), create=True)
    report = (tmp_path/'.test-artifacts/production-transfer-result.json').read_text()
    assert 'PRODUCTION_PLAN_CHANGED' in report
    assert 'SECRET' not in report+result and 'private-uri' not in report+result


def test_full_runner_real_commit_and_postcommit_verification(tmp_path, prepared, monkeypatch):
    admin = local_admin()
    name = 'academy_transfer_'+uuid4().hex[:12]+'_test'
    manager = make_engine(admin.render_as_string(hide_password=False))
    with manager.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    target = admin.set(database=name)
    engine = make_engine(target.render_as_string(hide_password=False))
    try:
        with engine.begin() as connection:
            make_auth(connection, prepared)
        prepared['folder'] = tmp_path
        monkeypatch.setattr(transfer, 'ROOT', tmp_path)
        monkeypatch.setattr(transfer, 'prepare_snapshot', lambda: prepared)
        monkeypatch.setattr(transfer, 'database_url', lambda *args: target.set(host='test.pooler.supabase.com',username='postgres.testref'))
        real_connect = transfer.psycopg.connect
        def connect(**kwargs):
            assert kwargs['sslmode'] == 'verify-full'
            kwargs.update(host=target.host, port=target.port, user=target.username)
            return real_connect(**kwargs)
        monkeypatch.setattr(transfer.psycopg, 'connect', connect)
        placeholder = 'postgresql://postgres.testref:[YOUR-DATABASE-PASSWORD]@test.pooler.supabase.com:5432/postgres'
        transfer.execute(target.query['sslrootcert'], (placeholder, 'unused'), create=True)
        report = json.loads((tmp_path/'.test-artifacts/production-transfer-result.json').read_text())
        assert report['status'] == 'passed', report
        assert report['commit_verified'] and report['total_xp'] == 40
        with engine.connect() as connection:
            assert transfer.verify_import(connection, prepared)['all_typed_values_match']
        # A repeated operation must refuse existing production schemas.
        transfer.execute(target.query['sslrootcert'], (placeholder, 'unused'), create=True)
        again = json.loads((tmp_path/'.test-artifacts/production-transfer-result.json').read_text())
        assert again['error'] == 'PRODUCTION_SCHEMAS_EXIST_NO_OVERWRITE'
    finally:
        engine.dispose()
        with manager.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        manager.dispose()
