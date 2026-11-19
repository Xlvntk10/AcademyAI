"""Approved first production migration + snapshot import; no publishing or role grants."""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
from uuid import UUID
import psycopg
import sqlalchemy as sa
from sqlmodel import Session
from app.database.cloud import copy_profile, read_profile, verify_profile
from app.services.analytics import dashboard
from scripts.check_postgres import database_url, driver_certificate, validate_visible_uri, ConfigurationError
from scripts.migrate_cloud import render_cloud_sql
from scripts.prepare_db import backup, snapshot, connect_readonly
from scripts.run_stage import transaction_body
from scripts.stage_diagnostics import safe_diagnostic

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ('academy', 'academy_auth', 'academy_migrations')
MIGRATION_HASH = 'bb8b5ed300d83507348d4b643c6b8997f9e853ed8cfb4b7739d719394ed2b818'


class TransferFailure(RuntimeError):
    """Only fixed safe error codes may be passed to this exception."""


def reviewed_plan():
    sql = render_cloud_sql()
    if hashlib.sha256(sql.encode('utf8')).hexdigest() != MIGRATION_HASH:
        raise TransferFailure('PRODUCTION_PLAN_CHANGED')
    return transaction_body(sql, 'COMMIT;')


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint(path):
    # WAL is part of the original's mutable state; never silently ignore it.
    return {suffix: file_hash(Path(str(path)+suffix)) if Path(str(path)+suffix).exists() else None
            for suffix in ('', '-wal', '-journal')}


def local_source():
    manifest = json.loads((ROOT/'backups/v6-20261119T001448Z/manifest.json').read_text(encoding='utf8'))
    candidates = [item for item in manifest if item.get('progress', {}).get('total_xp') == 40]
    if len(candidates) != 1:
        raise TransferFailure('LOCAL_PROFILE_AMBIGUOUS')
    source = Path(candidates[0]['source']).resolve()
    user_id = str(UUID(source.stem))
    registry = source.parent/'sessions.sqlite3'
    with connect_readonly(registry) as conn:
        emails = conn.execute('SELECT DISTINCT lower(email) FROM sessions WHERE user_id=?', (user_id,)).fetchall()
        realms = conn.execute('SELECT realm FROM account_meta').fetchall()
    if len(emails) != 1 or len(realms) != 1:
        raise TransferFailure('LOCAL_ACCOUNT_IDENTITY_AMBIGUOUS')
    return source, user_id, emails[0][0], realms[0][0]


def prepare_snapshot():
    source, user_id, email, realm = local_source()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT/'backups'/('production-'+stamp)
    folder.mkdir(parents=True)
    before = source_fingerprint(source)
    saved = folder/'profile-40xp.db'
    backup(source, saved)
    if snapshot(source) != snapshot(saved) or source_fingerprint(source) != before:
        raise TransferFailure('LOCAL_PROFILE_CHANGED_DURING_BACKUP')
    # Preserve the old profile and session registry locally, never upload them.
    backup(ROOT/'database.db', folder/'legacy-profile.db')
    backup(source.parent/'sessions.sqlite3', folder/'sessions.sqlite3')
    profile = read_profile(saved)
    engine = sa.create_engine('sqlite://', creator=lambda: sqlite3.connect(saved.as_uri()+'?mode=ro', uri=True))
    try:
        with Session(engine) as session:
            progress = dashboard(session)
            if progress['total_xp'] != 40:
                raise TransferFailure('LOCAL_EXPECTED_40_XP_MISMATCH')
    finally:
        engine.dispose()
    # Private recovery manifest contains no tokens, email or connection URI.
    (folder/'manifest.json').write_text(json.dumps({
        'source':str(source), 'source_fingerprint':before, 'backup_sha256':file_hash(saved),
        'total_xp':40, 'row_counts':{name:len(rows) for name,rows in profile.items()},
        'note':'Original profile is preserved; this is a snapshot, not ongoing synchronization.'
    }, indent=2), encoding='utf8')
    return {'source':source, 'saved':saved, 'folder':folder, 'fingerprint':before,
            'user_id':user_id, 'email':email, 'realm':realm, 'profile':profile}


def assert_source_unchanged(prepared):
    if source_fingerprint(prepared['source']) != prepared['fingerprint'] or snapshot(prepared['source']) != snapshot(prepared['saved']):
        raise TransferFailure('LOCAL_PROFILE_CHANGED_STOP_AND_REVIEW')


def validate_project(url, realm):
    if not url.host.endswith('.pooler.supabase.com') or '.' not in url.username:
        raise TransferFailure('SUPABASE_SESSION_POOLER_REQUIRED')
    project = url.username.rsplit('.', 1)[1]
    expected = hashlib.sha256(('https://'+project+'.supabase.co').encode()).hexdigest()[:16]
    if expected != realm:
        raise TransferFailure('SUPABASE_PROJECT_DOES_NOT_MATCH_LOCAL_ACCOUNT')


def preflight(connection, user_id, email):
    present = connection.execute(sa.text('SELECT nspname FROM pg_namespace WHERE nspname=ANY(:names)'), {'names':list(SCHEMAS)}).scalars().all()
    if present:
        raise TransferFailure('PRODUCTION_SCHEMAS_EXIST_NO_OVERWRITE')
    if not connection.exec_driver_sql("SELECT has_database_privilege(current_user,current_database(),'CREATE')").scalar_one():
        raise TransferFailure('PRODUCTION_CREATE_PRIVILEGE_MISSING')
    # Read one identity only. No Auth changes, tokens, or whole-user export.
    matched = connection.execute(sa.text('''SELECT count(*) FROM auth.users
        WHERE id=CAST(:id AS uuid) AND lower(email)=:email AND email_confirmed_at IS NOT NULL'''),
        {'id':user_id, 'email':email}).scalar_one()
    if matched != 1:
        raise TransferFailure('SUPABASE_CONFIRMED_ACCOUNT_MISMATCH')
    return {'production_schemas_absent':True, 'confirmed_account_matches':True}


def outside_catalog(connection):
    return connection.execute(sa.text('''SELECT n.nspname,c.relname,c.relkind,c.oid
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
        AND n.nspname <> ALL(:names) ORDER BY n.nspname,c.relname,c.oid'''), {'names':list(SCHEMAS)}).fetchall()


def isolate_new_schemas(connection):
    connection.exec_driver_sql('''REVOKE ALL ON ALL TABLES IN SCHEMA academy, academy_auth, academy_migrations FROM PUBLIC;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA academy FROM PUBLIC;
        DO $isolate$ DECLARE api_role text; BEGIN
        FOREACH api_role IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
                EXECUTE format('REVOKE ALL ON SCHEMA academy, academy_auth, academy_migrations FROM %I', api_role);
                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA academy, academy_auth, academy_migrations FROM %I', api_role);
                EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA academy FROM %I', api_role);
            END IF;
        END LOOP; END $isolate$;''', execution_options={'no_parameters':True})


def verify_import(connection, prepared):
    exposed = connection.execute(sa.text('''SELECT count(*) FROM (
        SELECT n.nspowner AS owner, a.grantee FROM pg_namespace n
        CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
        WHERE n.nspname=ANY(:names)
        UNION ALL
        SELECT c.relowner AS owner, a.grantee FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,
            acldefault(CASE WHEN c.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,c.relowner))) a
        WHERE n.nspname=ANY(:names) AND c.relkind IN ('r','S')
        ) grants WHERE grantee <> owner'''), {'names':list(SCHEMAS)}).scalar_one()
    if exposed:
        raise TransferFailure('UNEXPECTED_PRODUCTION_ACCESS_GRANT')
    counts = verify_profile(connection, prepared['user_id'], prepared['profile'])
    if connection.exec_driver_sql('SELECT count(*) FROM academy_auth.users').scalar_one() != 1:
        raise TransferFailure('UNEXPECTED_PRODUCTION_OWNERS')
    for name in prepared['profile']:
        if connection.exec_driver_sql(f'SELECT count(*) FROM academy."{name}"').scalar_one() != counts[name]:
            raise TransferFailure('UNEXPECTED_PRODUCTION_ROWS')
    for table in ('sessions','auth_limits'):
        if connection.exec_driver_sql(f'SELECT count(*) FROM academy_auth.{table}').scalar_one() != 0:
            raise TransferFailure('SESSIONS_MUST_NOT_BE_IMPORTED')
    if connection.exec_driver_sql('SELECT realm FROM academy_auth.meta WHERE id=1').scalar_one() != prepared['realm']:
        raise TransferFailure('CLOUD_REALM_MISMATCH')
    forced = connection.exec_driver_sql("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='academy' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity""").scalar_one()
    if forced != 21:
        raise TransferFailure('PRODUCTION_FORCE_RLS_MISSING')
    if connection.exec_driver_sql("SELECT version_num FROM academy_migrations.alembic_version").scalar_one() != 'cloud_0001':
        raise TransferFailure('PRODUCTION_REVISION_MISMATCH')
    # No writes: analytics only, and only the single verified imported owner exists.
    connection.execution_options(schema_translate_map={None:'academy'})
    try:
        with Session(bind=connection, info={'account':{'id':prepared['user_id']}}, join_transaction_mode='create_savepoint') as session:
            stats = dashboard(session)
            if stats['total_xp'] != 40:
                raise TransferFailure('CLOUD_EXPECTED_40_XP_MISMATCH')
    finally:
        connection.execution_options(schema_translate_map=None)
    return {'total_xp':40, 'tables_compared':len(counts), 'row_counts':counts,
            'completed_lessons':stats['completed_lessons'], 'completed_runs':stats['completed_runs'],
            'force_rls_tables':forced, 'sessions_imported':False, 'all_typed_values_match':True,
            'explicit_access_owner_only':True, 'runtime_role_created':False}


def apply_and_import(connection, prepared, plan, progress=lambda phase: None):
    progress('IDENTITY_AND_DESTINATION')
    connection.exec_driver_sql("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='60s'")
    connection.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtextextended('academy-first-production-import', 0))")
    preflight(connection, prepared['user_id'], prepared['email'])
    before = outside_catalog(connection)
    progress('CREATE_PRODUCTION_SCHEMAS')
    connection.exec_driver_sql(plan, execution_options={'no_parameters':True})
    isolate_new_schemas(connection)
    progress('IMPORT_PROFILE_COPY')
    connection.execute(sa.text('INSERT INTO academy_auth.users(user_id) VALUES (:id)'), {'id':prepared['user_id']})
    connection.execute(sa.text('INSERT INTO academy_auth.meta(id,realm) VALUES (1,:realm)'), {'realm':prepared['realm']})
    copy_profile(connection, prepared['user_id'], prepared['profile'])
    for name in sorted(prepared['profile']):
        if connection.execute(sa.text('SELECT to_regclass(:name)'), {'name':f'academy.{name}_id_seq'}).scalar_one():
            connection.exec_driver_sql(f'''SELECT setval('academy.{name}_id_seq',
                GREATEST((SELECT last_value FROM academy.{name}_id_seq), COALESCE((SELECT max(id) FROM academy."{name}"),1)), true)''')
    progress('VERIFY_IMPORTED_VALUES')
    result = verify_import(connection, prepared)
    assert_source_unchanged(prepared)
    if outside_catalog(connection) != before:
        raise TransferFailure('OUTSIDE_CATALOG_CHANGED')
    return {**result, 'outside_catalog_unchanged':True, 'role_grants_changed':False}


def execute(ca_file, credentials, *, create=False, progress=lambda phase: None):
    """Credentials come only from the local GUI; report only safe data."""
    logging.disable(logging.CRITICAL)
    report = {'status':'not_started', 'supabase_confirmed':False}
    phase = 'PLAN_CHECK'
    commit_started = False
    commit_returned = False
    engine = None
    prepared = None
    def step(value):
        nonlocal phase
        phase = value
        progress(value)
    try:
        plan = reviewed_plan()
        step('LOCAL_BACKUP')
        prepared = prepare_snapshot()
        step('CONFIGURATION')
        uri, password = credentials
        url = database_url(validate_visible_uri(uri), password, ca_file)
        validate_project(url, prepared['realm'])
        with ExitStack() as resources:
            ca = resources.enter_context(driver_certificate(url.query['sslrootcert']))
            def connect():
                conn = psycopg.connect(host=url.host, port=5432, dbname=url.database, user=url.username,
                    password=url.password, sslmode='verify-full', sslrootcert=ca,
                    ssl_min_protocol_version='TLSv1.2', gssencmode='disable', options='',
                    connect_timeout=15, prepare_threshold=None, application_name='academy-approved-profile-import')
                if not conn.pgconn.ssl_in_use:
                    conn.close()
                    raise TransferFailure('TLS_REQUIRED')
                conn.read_only = True
                return conn
            engine = sa.create_engine('postgresql+psycopg://', creator=connect,
                poolclass=sa.pool.NullPool, hide_parameters=True)
            step('READ_ONLY_PREFLIGHT')
            with engine.connect() as connection:
                with connection.begin():
                    inspection = preflight(connection, prepared['user_id'], prepared['email'])
                if not create:
                    report = {'status':'inspection_passed','supabase_confirmed':False,'mode':'read_only',**inspection}
                else:
                    connection.connection.driver_connection.read_only = False
                    with connection.begin() as transaction:
                        details = apply_and_import(connection, prepared, plan, step)
                        step('COMMIT')
                        commit_started = True
                        transaction.commit()
                        commit_returned = True
                    connection.connection.driver_connection.read_only = True
                    step('VERIFY_AFTER_COMMIT')
                    with connection.begin():
                        verified = verify_import(connection, prepared)
                    assert_source_unchanged(prepared)
                    report = {'status':'passed','supabase_confirmed':True,'tls':'verify-full',
                        'commit_verified':True,'source_unchanged':True,'source_write_lock':False,
                        'backup_verified':True, **details, **verified}
    except TransferFailure as error:
        report['error'] = str(error)
    except ConfigurationError:
        report['error'] = 'CONFIGURATION_REVIEW_INPUT'
    except Exception as error:
        report['diagnostic'] = safe_diagnostic(error, phase)
        report['error'] = report['diagnostic']['code']
    finally:
        if engine is not None:
            engine.dispose()
    if report['status'] == 'not_started':
        report['status'] = ('committed_verification_failed_do_not_retry' if commit_returned else
            'commit_unconfirmed_do_not_retry' if commit_started else 'failed_no_commit_requested')
        report['phase'] = phase
    if prepared:
        report['backup_folder'] = str(prepared['folder'].relative_to(ROOT))
    directory = ROOT/'.test-artifacts'
    directory.mkdir(exist_ok=True)
    name = 'production-transfer-result.json' if create else 'production-transfer-inspection.json'
    (directory/name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    if report['status'] == 'passed':
        return 'Перенос завершён: 40 XP, все записи сверены после фиксации. Исходник и резервные копии сохранены.'
    if report['status'] == 'inspection_passed':
        return 'Проверка пройдена: аккаунт совпадает, рабочие схемы отсутствуют. Запись в Supabase не выполнялась.'
    return 'Остановка: '+report['status']+' / '+report.get('error','UNKNOWN')+'. Не повторяйте перенос до проверки отчёта.'
