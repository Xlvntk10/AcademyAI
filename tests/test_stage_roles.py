"""Regression: SET ROLE checks session_user, not just current_user."""
import os
import pytest
import sqlalchemy as sa
from app.database.db import make_engine
from scripts.run_stage import reviewed_sql, transaction_body
from scripts.stage_diagnostics import safe_diagnostic
from scripts.check_postgres import diagnose


@pytest.fixture
def strict_creator():
    url = os.environ.get('ACADEMY_TEST_ADMIN_URL')
    if not url:
        pytest.skip('Local PostgreSQL required')
    parsed = sa.engine.make_url(url)
    if parsed.host not in ('127.0.0.1','localhost') or not parsed.database.endswith('_test'):
        pytest.fail('Only isolated loopback PostgreSQL is permitted')
    engine = make_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if connection.dialect.server_version_info < (16,):
                pytest.skip('Explicit membership SET option needs PostgreSQL 16+')
            # New local fixture, entirely rolled back; never a Supabase role.
            connection.exec_driver_sql('CREATE ROLE academy_stage_session_test NOLOGIN CREATEROLE CREATEDB BYPASSRLS')
            db = connection.dialect.identifier_preparer.quote(parsed.database)
            connection.exec_driver_sql(f'GRANT CREATE ON DATABASE {db} TO academy_stage_session_test')
            connection.exec_driver_sql('SET LOCAL SESSION AUTHORIZATION academy_stage_session_test')
            connection.exec_driver_sql("SET LOCAL createrole_self_grant = ''")
            assert connection.exec_driver_sql('SELECT current_user = session_user').scalar_one()
            assert not connection.exec_driver_sql('SELECT rolsuper FROM pg_roles WHERE rolname=session_user').scalar_one()
            yield connection
        finally:
            transaction.rollback()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname IN ('academy_stage','academy_stage_auth','academy_stage_migrations')").scalar_one() == 0
        assert not connection.exec_driver_sql("SELECT 1 FROM pg_roles WHERE rolname IN ('academy_stage_runtime','academy_stage_session_test')").first()
    engine.dispose()


def test_original_plan_reproduces_set_role_42501_and_old_unknown(strict_creator):
    connection = strict_creator
    plans = reviewed_sql()
    connection.exec_driver_sql(transaction_body(plans['01_schema.sql'],'COMMIT;'), execution_options={'no_parameters':True})
    assert connection.exec_driver_sql("SELECT bool_or(m.admin_option) FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member JOIN pg_roles parent ON parent.oid=m.roleid WHERE member.rolname=session_user AND parent.rolname='academy_stage_runtime'").scalar_one()
    assert not connection.exec_driver_sql("SELECT pg_has_role(session_user,'academy_stage_runtime','SET')").scalar_one()
    with pytest.raises(sa.exc.DBAPIError) as failure, connection.begin_nested():
        connection.exec_driver_sql(transaction_body(plans['02_smoke_rollback.sql'],'ROLLBACK;'), execution_options={'no_parameters':True})
    assert failure.value.orig.sqlstate == '42501'
    assert diagnose(failure.value) == 'UNKNOWN'
    assert safe_diagnostic(failure.value,'RLS_SMOKE')['code'] == 'ROLE_SWITCH_DENIED'


def test_preflight_stops_before_any_stage_ddl_without_set(strict_creator):
    from scripts.run_stage import apply_and_test, StageFailure
    from scripts.stage_role_checks import creation_capabilities
    capabilities = creation_capabilities(strict_creator)
    assert capabilities['can_create_schema'] and capabilities['can_create_role']
    assert not capabilities['session_superuser']
    assert not capabilities['creator_auto_set']
    assert not capabilities['new_role_set_expected']
    with pytest.raises(StageFailure, match='STAGE_SET_ROLE_APPROVAL_REQUIRED'):
        apply_and_test(strict_creator, reviewed_sql())
    assert strict_creator.exec_driver_sql("SELECT count(*) FROM pg_namespace WHERE nspname IN ('academy_stage','academy_stage_auth','academy_stage_migrations')").scalar_one() == 0
    assert not strict_creator.exec_driver_sql("SELECT 1 FROM pg_roles WHERE rolname='academy_stage_runtime'").first()


def test_proposed_set_grant_locally_fixes_rls_and_xp_without_bypass(strict_creator):
    from pathlib import Path
    from scripts.stage_role_checks import restricted_role_evidence
    from scripts.stage_learning_trial import learning_trial
    connection = strict_creator
    plans = reviewed_sql()
    connection.exec_driver_sql(transaction_body(plans['01_schema.sql'],'COMMIT;'), execution_options={'no_parameters':True})
    assert not connection.exec_driver_sql("SELECT pg_has_role(session_user,'academy_stage_runtime','SET')").scalar_one()
    # Explicit local rehearsal of the proposal, NOT part of the real executor.
    proposal = Path('deploy/stage/creator_set_role.proposed.sql').read_text(encoding='utf-8-sig')
    connection.exec_driver_sql(proposal, execution_options={'no_parameters':True})
    flags = connection.exec_driver_sql("""SELECT bool_or(m.set_option) AS set_option,bool_or(m.inherit_option) AS inherit_option
        FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member
        JOIN pg_roles parent ON parent.oid=m.roleid
        WHERE member.rolname=session_user AND parent.rolname='academy_stage_runtime'""").one()
    assert flags.set_option is True and flags.inherit_option is False
    for trial in ('smoke','learning'):
        with connection.begin_nested() as test_data:
            evidence = restricted_role_evidence(connection)
            assert evidence == {'role':'academy_stage_runtime','bypassrls':False,'superuser':False,'login':False,'row_security':True}
            if trial == 'smoke':
                connection.exec_driver_sql(transaction_body(plans['02_smoke_rollback.sql'],'ROLLBACK;'), execution_options={'no_parameters':True})
            else:
                result = learning_trial(connection)
                assert result['synthetic_xp'] == result['replayed_xp'] == 60
                assert result['other_account_xp'] == 0
            test_data.rollback()
    assert connection.exec_driver_sql('SELECT count(*) FROM academy_stage_auth.users').scalar_one() == 0
