"""Local-only verification of the approved Supabase stage executor."""
import os
import json
from pathlib import Path
import pytest
import sqlalchemy as sa
from app.database.db import make_engine
from scripts import run_stage


@pytest.fixture(params=[False, True], ids=["local-admin", "non-superuser"])
def admin_connection(request):
    url = os.environ.get('ACADEMY_TEST_ADMIN_URL')
    if not url:
        pytest.skip('Local PostgreSQL test URL required')
    parsed = sa.engine.make_url(url)
    if parsed.host not in ('127.0.0.1', 'localhost', '::1') or not parsed.database.endswith('_test'):
        pytest.fail('Only local *_test database allowed')
    engine = make_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if request.param:
                connection.exec_driver_sql('CREATE ROLE academy_stage_runner_test NOLOGIN CREATEROLE')
                name = connection.dialect.identifier_preparer.quote(parsed.database)
                connection.exec_driver_sql(f'GRANT CREATE ON DATABASE {name} TO academy_stage_runner_test')
                connection.exec_driver_sql('SET LOCAL ROLE academy_stage_runner_test')
            yield connection
        finally:
            transaction.rollback()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname IN ('academy_stage','academy_stage_auth','academy_stage_migrations')").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM pg_roles WHERE rolname='academy_stage_runtime'").scalar_one() == 0
    engine.dispose()


def test_full_executor_grading_replay_and_rollback(admin_connection):
    statements = []
    def record(conn, cursor, sql, params, context, many):
        statements.append(sql)
    sa.event.listen(admin_connection, 'before_cursor_execute', record)
    result = run_stage.apply_and_test(admin_connection, run_stage.reviewed_sql())
    assert result['test_rows_after_rollback'] == 0
    assert result['learning_trial']['synthetic_xp'] == 60
    assert result['learning_trial']['replayed_xp'] == 60
    assert result['learning_trial']['other_account_xp'] == 0
    # ORM-generated learning writes must resolve explicitly to the staging schema.
    writes = [s for s in statements if s.startswith(('INSERT INTO ', 'UPDATE ', 'DELETE FROM '))]
    assert writes
    assert all(s.startswith(('INSERT INTO academy_stage.', 'INSERT INTO academy_stage_auth.',
                             'UPDATE academy_stage.', 'DELETE FROM academy_stage.')) for s in writes)
    with pytest.raises(run_stage.StageFailure, match='STAGE_ALREADY_EXISTS'), admin_connection.begin_nested():
        run_stage.apply_and_test(admin_connection, run_stage.reviewed_sql())


def test_failure_rolls_back_stage_ddl_and_role(admin_connection, monkeypatch):
    def fail(connection):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr('scripts.stage_learning_trial.learning_trial', fail)
    with pytest.raises(RuntimeError, match='synthetic failure'), admin_connection.begin_nested():
        run_stage.apply_and_test(admin_connection, run_stage.reviewed_sql())
    assert admin_connection.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname IN ('academy_stage','academy_stage_auth','academy_stage_migrations')").scalar_one() == 0
    assert admin_connection.exec_driver_sql("SELECT count(*) FROM pg_roles WHERE rolname='academy_stage_runtime'").scalar_one() == 0


def test_changed_plan_refused_before_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_stage, 'ROOT', tmp_path)
    folder = tmp_path/'deploy/stage'
    folder.mkdir(parents=True)
    for name in run_stage.PINNED:
        (folder/name).write_text('altered SQL')
    monkeypatch.setattr(run_stage, 'visible_uri', lambda: pytest.fail('No credential input for changed SQL'))
    assert run_stage.main(['--ca-file', 'not-used']) == 1
    assert 'PLAN_CHANGED' in capsys.readouterr().out


def test_raw_connection_error_is_never_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_stage, 'ROOT', tmp_path)
    monkeypatch.setattr(run_stage, 'reviewed_sql', lambda: {})
    def failure():
        raise RuntimeError('postgresql://name:REAL_SECRET@private-host/postgres')
    monkeypatch.setattr(run_stage, 'visible_uri', failure)
    assert run_stage.main(['--ca-file', 'not-used']) == 1
    output = capsys.readouterr()
    report = (tmp_path/'.test-artifacts/supabase-stage-result.json').read_text()
    for secret in ('REAL_SECRET', 'private-host', 'postgresql://'):
        assert secret not in output.out + output.err + report
    assert json.loads(report)['supabase_confirmed'] is False
