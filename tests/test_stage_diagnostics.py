"""Safe diagnostics and a CLI path that cannot execute migrations."""
import json
import os
from pathlib import Path
import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from scripts import run_stage
from scripts.stage_diagnostics import safe_diagnostic
from scripts.stage_state import inspect_stage


@pytest.mark.parametrize('driver,code,state', [
    (psycopg.errors.InsufficientPrivilege('permission denied to set role SECRET'), 'ROLE_SWITCH_DENIED', '42501'),
    (psycopg.errors.InsufficientPrivilege('permission denied to create role SECRET'), 'ROLE_CREATE_DENIED', '42501'),
    (psycopg.errors.InsufficientPrivilege('permission denied for schema SECRET'), 'INSUFFICIENT_PRIVILEGE', '42501'),
    (psycopg.errors.SyntaxError('SQL SECRET'), 'SQL_SYNTAX', '42601'),
    (psycopg.errors.ReadOnlySqlTransaction('SECRET'), 'READ_ONLY_VIOLATION', '25006'),
    (psycopg.errors.ForeignKeyViolation('SECRET'), 'FOREIGN_KEY', '23503'),
    (psycopg.errors.QueryCanceled('SECRET'), 'QUERY_CANCELLED', '57014'),
    (psycopg.errors.InvalidPassword('SECRET'), 'AUTH_REJECTED', '28P01'),
    (psycopg.OperationalError('certificate verify failed SECRET'), 'TLS_CERTIFICATE', None),
])
def test_unwrap_sqlalchemy_and_redact(driver, code, state):
    wrapped = sa.exc.ProgrammingError('SQL SECRET', {'password':'SECRET'}, driver)
    result = safe_diagnostic(wrapped, 'STAGE_DDL')
    assert result['code'] == code
    assert result['sqlstate'] == state
    assert result['phase'] == 'STAGE_DDL'
    assert 'SECRET' not in json.dumps(result)


def test_local_error_reports_type_not_arbitrary_message():
    result = safe_diagnostic(TypeError('postgresql://name:SECRET@host/db'), 'SQLALCHEMY_INITIALIZE')
    assert result['code'] == 'LOCAL_TYPE_OR_VALUE'
    assert result['exception_family'] == 'TypeError'
    assert 'SECRET' not in json.dumps(result)


def local_url():
    value = os.environ.get('ACADEMY_TEST_ADMIN_URL')
    if not value:
        pytest.skip('Local PostgreSQL required')
    parsed = make_url(value)
    if parsed.host not in {'localhost','127.0.0.1'} or not parsed.database.endswith('_test'):
        pytest.fail('Local test database only')
    return parsed


def test_inspection_cli_real_creator_is_readonly(tmp_path, monkeypatch, capsys):
    url = local_url()
    monkeypatch.setattr(run_stage, 'ROOT', tmp_path)
    old = tmp_path/'.test-artifacts/supabase-stage-result.json'
    old.parent.mkdir()
    old.write_text('{"status":"failed_no_commit_requested","error":"UNKNOWN"}')
    def forbidden(*args, **kwargs):
        pytest.fail('Inspection must not load or execute the migration plan')
    monkeypatch.setattr(run_stage, 'reviewed_sql', forbidden)
    monkeypatch.setattr(run_stage, 'apply_and_test', forbidden)
    monkeypatch.setattr(run_stage, 'visible_uri', lambda: 'placeholder')
    monkeypatch.setattr(run_stage, 'hidden', lambda _: 'unused')
    # CLI validation sees a permitted endpoint; the actual test connection is local.
    monkeypatch.setattr(run_stage, 'database_url', lambda *args: url.set(host='test.pooler.supabase.com'))
    real_connect = psycopg.connect
    seen = []
    def local_connect(**kwargs):
        assert kwargs['sslmode'] == 'verify-full'
        assert kwargs['gssencmode'] == 'disable'
        kwargs.update(host=url.host,port=url.port)
        conn = real_connect(**kwargs)
        seen.append(conn)
        return conn
    monkeypatch.setattr(run_stage.psycopg, 'connect', local_connect)
    real_inspect = inspect_stage
    def inspect_and_assert(connection):
        assert connection.exec_driver_sql('SHOW transaction_read_only').scalar_one() == 'on'
        # A zero-row write to the local test registry must still be rejected by PG.
        with pytest.raises(sa.exc.DBAPIError) as error, connection.begin_nested():
            connection.exec_driver_sql('DELETE FROM academy_auth.auth_limits WHERE false')
        assert error.value.orig.sqlstate == '25006'
        return real_inspect(connection)
    monkeypatch.setattr('scripts.stage_state.inspect_stage', inspect_and_assert)
    assert run_stage.main(['--inspect','--ca-file',url.query['sslrootcert']]) == 0
    report = json.loads((old.parent/'supabase-stage-inspection.json').read_text())
    assert report['status'] == 'inspection_passed'
    assert report['state'] == 'absent'
    assert report['transaction_read_only'] is True
    assert report['personal_rows_read'] is False
    assert json.loads(old.read_text())['error'] == 'UNKNOWN'  # Preserve prior evidence.
    assert all(c.closed for c in seen)
    output = capsys.readouterr()
    assert url.password not in output.out + output.err


def test_inspector_refuses_write_enabled_transaction():
    from app.database.db import make_engine
    engine = make_engine(local_url().render_as_string(hide_password=False))
    try:
        with engine.begin() as connection:
            with pytest.raises(RuntimeError,match='READ_ONLY_REQUIRED'):
                inspect_stage(connection)
    finally:
        engine.dispose()


def test_readonly_failure_does_not_claim_rollback_or_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_stage, 'ROOT', tmp_path)
    def fail():
        raise psycopg.OperationalError('certificate verify failed SECRET')
    monkeypatch.setattr(run_stage, 'visible_uri', fail)
    assert run_stage.main(['--inspect','--ca-file','not-used']) == 1
    report = json.loads((tmp_path/'.test-artifacts/supabase-stage-inspection.json').read_text())
    assert report['status'] == 'inspection_failed_no_writes'
    assert report['cloud_state'] == 'not_confirmed_by_this_run'
    assert report['error'] == 'TLS_CERTIFICATE'
    assert 'SECRET' not in json.dumps(report) + capsys.readouterr().err
