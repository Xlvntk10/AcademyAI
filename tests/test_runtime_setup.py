"""Real PostgreSQL tests; synthetic profiles and local *_test DB only."""
import secrets
import pytest
import sqlalchemy as sa
from scripts import runtime_setup as runtime
from scripts import production_transfer as transfer
from tests.test_production_transfer import prepared, empty_destination, local_admin, make_auth


@pytest.fixture(autouse=True)
def isolate_existing_test_role(empty_destination):
    # The shared LOCAL test cluster already uses this name. Rename transactionally
    # along with the fixture's old schemas; its final rollback restores everything.
    if runtime.role_exists(empty_destination):
        empty_destination.exec_driver_sql('ALTER ROLE academy_runtime RENAME TO academy_runtime_saved_test')


def ready(connection, prepared):
    transfer.apply_and_import(connection,prepared,transfer.reviewed_plan())


def test_runtime_role_grants_rls_and_rollback(empty_destination,prepared):
    connection = empty_destination
    ready(connection,prepared)
    baseline = runtime.external_permissions(connection)
    runtime.create_role(connection,secrets.token_urlsafe(36))
    assert runtime.external_permissions(connection) == baseline
    # Superuser is used only to change session authorization. The actual checks
    # require BOTH current_user and session_user to be the restricted role.
    connection.exec_driver_sql('SET SESSION AUTHORIZATION academy_runtime')
    try:
        nested = connection.begin_nested()
        details,marker = runtime.runtime_trial(connection,prepared)
        nested.rollback()
        assert details['total_xp'] == 40 and details['tables_compared'] == 21
        assert details['rls_other_owner_hidden'] and details['rls_write_rejected']
        assert connection.execute(sa.text('SELECT count(*) FROM academy_auth.auth_limits WHERE bucket=:key'),{'key':marker}).scalar_one() == 0
        runtime.verify_data(connection,prepared)
    finally:
        connection.exec_driver_sql('RESET SESSION AUTHORIZATION')
    transfer.assert_source_unchanged(prepared)


def test_existing_role_never_reset(empty_destination,prepared):
    ready(empty_destination,prepared)
    runtime.create_role(empty_destination,secrets.token_urlsafe(36))
    with pytest.raises(runtime.RuntimeFailure,match='EXISTS_NO_OVERWRITE'):
        runtime.create_role(empty_destination,secrets.token_urlsafe(36))


def test_role_creation_rolls_back(empty_destination,prepared):
    ready(empty_destination,prepared)
    nested = empty_destination.begin_nested()
    runtime.create_role(empty_destination,secrets.token_urlsafe(36))
    nested.rollback()
    assert not runtime.role_exists(empty_destination)
    transfer.verify_import(empty_destination,prepared)


@pytest.mark.parametrize('unsafe',[
    'ALTER ROLE academy_runtime BYPASSRLS',
    'GRANT CREATE ON SCHEMA academy TO academy_runtime',
    'GRANT UPDATE ON academy_migrations.alembic_version TO academy_runtime',
    'GRANT SELECT ON auth.users TO academy_runtime',
    'GRANT pg_read_all_data TO academy_runtime',
])
def test_excess_privileges_rejected(empty_destination,prepared,unsafe):
    ready(empty_destination,prepared)
    runtime.create_role(empty_destination,secrets.token_urlsafe(36))
    empty_destination.exec_driver_sql(unsafe)
    with pytest.raises(runtime.RuntimeFailure):
        runtime.check_role(empty_destination)


def test_admin_cannot_masquerade_as_login(empty_destination,prepared):
    ready(empty_destination,prepared)
    runtime.create_role(empty_destination,secrets.token_urlsafe(36))
    empty_destination.exec_driver_sql('SET LOCAL ROLE academy_runtime')
    try:
        with pytest.raises(runtime.RuntimeFailure,match='ACTUAL_RUNTIME_LOGIN_REQUIRED'):
            runtime.runtime_trial(empty_destination,prepared)
    finally:
        empty_destination.exec_driver_sql('RESET ROLE')


def test_short_password_stops_before_role(empty_destination,prepared):
    ready(empty_destination,prepared)
    with pytest.raises(runtime.RuntimeFailure,match='PASSWORD_TOO_SHORT'):
        runtime.create_role(empty_destination,'short-test-only')
    assert not runtime.role_exists(empty_destination)


def test_nonsuperuser_creator_needs_no_extra_set_grant(empty_destination,prepared):
    connection = empty_destination
    ready(connection,prepared)
    connection.exec_driver_sql('CREATE ROLE academy_creator_login_test NOLOGIN NOINHERIT CREATEROLE')
    connection.exec_driver_sql('GRANT USAGE ON SCHEMA academy,academy_auth,academy_migrations TO academy_creator_login_test WITH GRANT OPTION')
    connection.exec_driver_sql('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA academy,academy_auth TO academy_creator_login_test WITH GRANT OPTION')
    connection.exec_driver_sql('GRANT SELECT ON ALL TABLES IN SCHEMA academy_migrations TO academy_creator_login_test WITH GRANT OPTION')
    connection.exec_driver_sql('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA academy TO academy_creator_login_test WITH GRANT OPTION')
    connection.exec_driver_sql('SET SESSION AUTHORIZATION academy_creator_login_test')
    try:
        connection.exec_driver_sql("SET LOCAL createrole_self_grant=''")
        runtime.create_role(connection,secrets.token_urlsafe(36))
        assert not connection.exec_driver_sql("SELECT pg_has_role(current_user,'academy_runtime','SET')").scalar_one()
        assert not connection.exec_driver_sql('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').scalar_one()
    finally:
        connection.exec_driver_sql('RESET SESSION AUTHORIZATION')


def test_public_diagnostic_reports_acl_and_schema_barrier_without_rows(empty_destination):
    from scripts.runtime_diagnostics import public_access
    connection = empty_destination
    connection.exec_driver_sql('CREATE SCHEMA runtime_diagnostic_test')
    connection.exec_driver_sql('CREATE TABLE runtime_diagnostic_test.private_rows(secret text)')
    connection.exec_driver_sql("INSERT INTO runtime_diagnostic_test.private_rows VALUES ('synthetic-do-not-export')")
    connection.exec_driver_sql('GRANT SELECT ON runtime_diagnostic_test.private_rows TO PUBLIC')
    rows = [r for r in public_access(connection) if r['schema']=='runtime_diagnostic_test']
    assert rows == [{'schema':'runtime_diagnostic_test','object':'private_rows','kind':'r',
                     'privilege':'SELECT','grant_option':False,'public_schema_usage':False,'extension':None}]
    assert 'synthetic-do-not-export' not in repr(rows)
    connection.exec_driver_sql('GRANT USAGE ON SCHEMA runtime_diagnostic_test TO PUBLIC')
    with connection.begin_nested():
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        rows = [r for r in public_access(connection) if r['schema']=='runtime_diagnostic_test']
        assert rows[0]['public_schema_usage'] is True


def test_public_diagnostic_does_not_disable_runtime_guard(empty_destination,prepared):
    from scripts.runtime_diagnostics import public_access
    ready(empty_destination,prepared)
    runtime.create_role(empty_destination,secrets.token_urlsafe(36))
    empty_destination.exec_driver_sql('GRANT SELECT ON auth.users TO PUBLIC')
    assert any(r['schema']=='auth' and r['object']=='users' for r in public_access(empty_destination))
    with pytest.raises(runtime.RuntimeFailure,match='RUNTIME_OUTSIDE_TABLE_ACCESS'):
        runtime.check_role(empty_destination)


@pytest.fixture
def statistics_views(empty_destination):
    # Real bundled PostgreSQL extension, in the isolated local transaction.
    empty_destination.exec_driver_sql('CREATE SCHEMA extensions')
    empty_destination.exec_driver_sql('CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions')
    return empty_destination


def test_builtin_stats_without_schema_usage_are_actually_inaccessible(statistics_views,prepared):
    connection = statistics_views
    ready(connection,prepared)
    baseline = runtime.external_permissions(connection)
    runtime.create_role(connection,secrets.token_urlsafe(36))
    rows = runtime.check_role(connection)
    assert len(rows) == 2
    assert all(not row['schema_usage'] for row in rows)
    connection.exec_driver_sql('SET SESSION AUTHORIZATION academy_runtime')
    try:
        nested = connection.begin_nested()
        result,_ = runtime.runtime_trial(connection,prepared)
        nested.rollback()
        assert result['system_view_denials_verified'] == 2
        assert result['total_xp'] == 40
    finally:
        connection.exec_driver_sql('RESET SESSION AUTHORIZATION')
    assert runtime.external_permissions(connection) == baseline


@pytest.mark.parametrize('grant',[
    'GRANT USAGE ON SCHEMA extensions TO academy_runtime',
    'GRANT USAGE ON SCHEMA extensions TO PUBLIC',
    'GRANT SELECT ON extensions.pg_stat_statements TO academy_runtime WITH GRANT OPTION',
    'GRANT UPDATE ON extensions.pg_stat_statements TO academy_runtime',
])
def test_stats_exception_rejects_real_access_or_broader_rights(statistics_views,prepared,grant):
    ready(statistics_views,prepared)
    runtime.create_role(statistics_views,secrets.token_urlsafe(36))
    statistics_views.exec_driver_sql(grant)
    with pytest.raises(runtime.RuntimeFailure,match='RUNTIME_OUTSIDE_TABLE_ACCESS') as failure:
        runtime.check_role(statistics_views)
    assert failure.value.outside_access


def test_familiar_view_name_is_not_enough(empty_destination,prepared):
    ready(empty_destination,prepared)
    runtime.create_role(empty_destination,secrets.token_urlsafe(36))
    empty_destination.exec_driver_sql('CREATE SCHEMA extensions')
    empty_destination.exec_driver_sql('CREATE VIEW extensions.pg_stat_statements AS SELECT 1 AS value')
    empty_destination.exec_driver_sql('GRANT SELECT ON extensions.pg_stat_statements TO PUBLIC')
    with pytest.raises(runtime.RuntimeFailure,match='RUNTIME_OUTSIDE_TABLE_ACCESS'):
        runtime.check_role(empty_destination)
