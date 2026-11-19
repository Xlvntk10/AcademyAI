"""Staging SQL is generated offline and rehearsed only on loopback *_test DBs."""
import os
import re
from pathlib import Path
import pytest
import sqlalchemy as sa
from scripts.stage_plan import stage_sql, smoke_sql, SCHEMAS, ROLE
from scripts.migrate_cloud import render_cloud_sql, migrate_cloud
from app.database.db import make_engine

ROOT = Path(__file__).resolve().parents[1]


def test_plan_is_current_and_rendering_never_connects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("SQL rendering must not open a database")
    monkeypatch.setattr('app.database.db.make_engine', forbidden)
    plan = stage_sql()
    assert plan == (ROOT/'deploy/stage/01_schema.sql').read_text(encoding='utf8')
    assert smoke_sql() == (ROOT/'deploy/stage/02_smoke_rollback.sql').read_text(encoding='utf8')
    assert not re.search(r'\bacademy(?:_auth|_migrations)?\b', plan)
    assert not re.search(r'\b(?:auth|storage|public)\.', plan)
    assert 'NOLOGIN NOINHERIT' in plan
    assert not re.search(r'\b(?:DROP|TRUNCATE|PASSWORD)\s', re.sub(r'--[^\n]*', '', plan), re.I)
    assert plan.count('FORCE ROW LEVEL SECURITY') == 21
    assert plan.count('ADD CONSTRAINT owner_fk') == 21
    assert len(re.findall(r'CREATE TABLE academy_stage\.', plan)) == 21
    assert len(re.findall(r'CREATE TABLE academy_stage_auth\.', plan)) == 4
    assert 'cloud_0001' in plan
    assert render_cloud_sql().count('ADD CONSTRAINT owner_fk') == 21


@pytest.fixture(params=[False, True], ids=["local-admin", "non-superuser-migrator"])
def stage(request):
    url = os.environ.get('ACADEMY_TEST_ADMIN_URL')
    if not url:
        pytest.skip('Dedicated local PostgreSQL not supplied')
    parsed = sa.engine.make_url(url)
    if parsed.host not in {'127.0.0.1', 'localhost', '::1'} or not (parsed.database or '').endswith('_test'):
        pytest.fail('Stage rehearsal only permits a loopback *_test database')
    migrate_cloud(url)
    engine = make_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # Keep even CREATE ROLE/SCHEMA inside the outer rollback transaction.
            if request.param:
                connection.exec_driver_sql('CREATE ROLE academy_stage_migrator_test NOLOGIN CREATEROLE')
                database = connection.dialect.identifier_preparer.quote(parsed.database)
                connection.exec_driver_sql(f'GRANT CREATE ON DATABASE {database} TO academy_stage_migrator_test')
                connection.exec_driver_sql('SET LOCAL SESSION AUTHORIZATION academy_stage_migrator_test')
                connection.exec_driver_sql("SET LOCAL createrole_self_grant = 'set'")
                assert connection.exec_driver_sql('SELECT current_user=session_user').scalar_one()
            # Emulate provider-wide default grants; the stage must remove them.
            for api_role in ('anon', 'authenticated', 'service_role'):
                if not connection.execute(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name':api_role}).first():
                    connection.exec_driver_sql(f'CREATE ROLE {api_role} NOLOGIN')
                connection.exec_driver_sql(f'ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO {api_role}')
                connection.exec_driver_sql(f'ALTER DEFAULT PRIVILEGES GRANT ALL ON SEQUENCES TO {api_role}')
            sql = stage_sql()
            body = sql[sql.index('BEGIN;') + len('BEGIN;'):].rstrip().removesuffix('COMMIT;')
            connection.exec_driver_sql(body, execution_options={"no_parameters": True})
            yield connection
        finally:
            transaction.rollback()
    with engine.connect() as connection:
        assert connection.execute(sa.text('SELECT count(*) FROM pg_namespace WHERE nspname = ANY(:names)'), {'names':list(SCHEMAS)}).scalar_one() == 0
        assert not connection.execute(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name':ROLE}).first()
    engine.dispose()


def test_stage_migration_keys_indexes_policies_and_grants(stage):
    inspector = sa.inspect(stage)
    original = inspector.get_table_names(schema='academy')
    assert set(original) == set(inspector.get_table_names(schema=SCHEMAS[0]))
    for table in original:
        assert inspector.get_pk_constraint(table, schema='academy')['constrained_columns'] == inspector.get_pk_constraint(table, schema=SCHEMAS[0])['constrained_columns']
        production_fks = inspector.get_foreign_keys(table, schema='academy')
        staging_fks = inspector.get_foreign_keys(table, schema=SCHEMAS[0])
        normalize = lambda rows: sorted((r['name'], r['constrained_columns'], r['referred_table'], r['referred_columns']) for r in rows)
        assert normalize(production_fks) == normalize(staging_fks), table
        assert all(fk['referred_schema'] in SCHEMAS for fk in staging_fks)
        normalize_indexes = lambda rows: sorted((r['name'], r['column_names'], r['unique']) for r in rows)
        assert normalize_indexes(inspector.get_indexes(table, schema='academy')) == normalize_indexes(inspector.get_indexes(table, schema=SCHEMAS[0]))
    assert stage.exec_driver_sql('SELECT version_num FROM academy_stage_migrations.alembic_version').scalar_one() == 'cloud_0001'
    role = stage.exec_driver_sql("SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolinherit FROM pg_roles WHERE rolname='academy_stage_runtime'").one()
    assert not any(role)
    for api_role in ('anon', 'authenticated', 'service_role'):
        assert not stage.execute(sa.text("SELECT has_schema_privilege(:role, 'academy_stage_auth', 'USAGE')"), {'role':api_role}).scalar_one()
        assert not stage.execute(sa.text("SELECT has_table_privilege(:role, 'academy_stage_auth.sessions', 'SELECT')"), {'role':api_role}).scalar_one()
        assert not stage.execute(sa.text("SELECT has_sequence_privilege(:role, 'academy_stage.lesson_id_seq', 'USAGE')"), {'role':api_role}).scalar_one()
    stage.exec_driver_sql('SET LOCAL ROLE academy_stage_runtime')
    assert not stage.exec_driver_sql("SELECT has_schema_privilege(current_user, 'academy_stage', 'CREATE')").scalar_one()
    assert not stage.exec_driver_sql("SELECT has_table_privilege(current_user, 'academy_stage_migrations.alembic_version', 'UPDATE')").scalar_one()
    assert not stage.exec_driver_sql("SELECT has_schema_privilege(current_user, 'academy', 'USAGE')").scalar_one()
    assert stage.exec_driver_sql('SELECT count(*) FROM academy_stage.lesson').scalar_one() == 0


def test_stage_synthetic_accounts_fk_rls_search_path_and_rollback(stage):
    sql = smoke_sql()
    body = sql[sql.index('BEGIN;') + len('BEGIN;'):].rstrip().removesuffix('ROLLBACK;')
    with stage.begin_nested() as test_rows:
        stage.exec_driver_sql(body, execution_options={"no_parameters": True})
        assert stage.exec_driver_sql('SHOW search_path').scalar_one() == 'academy_stage, pg_catalog'
        test_rows.rollback()
    assert stage.exec_driver_sql('SELECT count(*) FROM academy_stage_auth.users').scalar_one() == 0
    assert stage.exec_driver_sql('SELECT count(*) FROM academy_stage.skill').scalar_one() == 0


def test_existing_stage_is_never_replaced(stage):
    sql = stage_sql()
    body = sql[sql.index('BEGIN;') + len('BEGIN;'):].rstrip().removesuffix('COMMIT;')
    with pytest.raises(sa.exc.DBAPIError, match='Stage already exists'), stage.begin_nested():
        stage.exec_driver_sql(body, execution_options={"no_parameters": True})
    assert stage.exec_driver_sql('SELECT version_num FROM academy_stage_migrations.alembic_version').scalar_one() == 'cloud_0001'
