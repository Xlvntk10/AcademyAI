"""First restricted backend login. No migrations, profile writes, or publication.

Admin and runtime passwords enter only through the local form. Reports contain
allowlisted evidence, never connection strings, SQL errors, or password hashes.
"""
from contextlib import ExitStack
import hashlib
import json
import logging
from uuid import uuid4

import psycopg
from psycopg import sql
import sqlalchemy as sa
from sqlmodel import Session

from app.database.cloud import set_owner, verify_profile
from app.services.analytics import dashboard
from scripts import production_transfer as transfer
from scripts.check_postgres import database_url, driver_certificate, validate_visible_uri, ConfigurationError
from scripts.stage_diagnostics import safe_diagnostic

ROOT = transfer.ROOT
ROLE = 'academy_runtime'
SCHEMAS = transfer.SCHEMAS


class RuntimeFailure(RuntimeError):
    """Messages must be fixed codes, not driver or user input."""

    def __init__(self, code, *, outside_access=None):
        super().__init__(code)
        self.outside_access = outside_access


def require(condition, code):
    if not condition:
        raise RuntimeFailure(code)


def role_exists(connection):
    return connection.exec_driver_sql("SELECT EXISTS(SELECT FROM pg_roles WHERE rolname='academy_runtime')").scalar_one()


def external_permissions(connection):
    # Include existing ACLs, policies and roles, not just table names.
    rows = connection.execute(sa.text('''SELECT n.nspname,c.relname,c.relkind,c.oid,
        c.relowner,c.relacl::text,c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
        AND n.nspname <> ALL(:names) ORDER BY n.nspname,c.relname,c.oid'''), {'names':list(SCHEMAS)}).fetchall()
    rows += connection.execute(sa.text('''SELECT nspname,nspowner,nspacl::text FROM pg_namespace
        WHERE nspname <> ALL(:names) ORDER BY nspname'''), {'names':list(SCHEMAS)}).fetchall()
    rows += connection.exec_driver_sql("""SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,
        rolcreatedb,rolinherit,rolcanlogin,rolreplication,rolconfig::text FROM pg_roles
        WHERE rolname <> 'academy_runtime' ORDER BY rolname""").fetchall()
    rows += connection.exec_driver_sql("""SELECT roleid,member,grantor,admin_option FROM pg_auth_members
        WHERE roleid <> COALESCE((SELECT oid FROM pg_roles WHERE rolname='academy_runtime'),0)
        AND member <> COALESCE((SELECT oid FROM pg_roles WHERE rolname='academy_runtime'),0)
        ORDER BY roleid,member,grantor""").fetchall()
    rows += connection.exec_driver_sql("""SELECT polrelid,polname,polcmd,polroles::text,
        polqual::text,polwithcheck::text FROM pg_policy ORDER BY polrelid,polname""").fetchall()
    rows += connection.execute(sa.text("""SELECT p.oid,p.proowner,p.proacl::text FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname <> ALL(:names)
        AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' ORDER BY p.oid"""), {'names':list(SCHEMAS)}).fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def outside_table_access(connection):
    return [dict(row) for row in connection.execute(sa.text("""SELECT n.nspname AS schema,
        c.relname AS object,c.relkind AS kind,e.extname AS extension,
        has_schema_privilege('academy_runtime',n.oid,'USAGE') AS schema_usage,
        has_table_privilege('academy_runtime',c.oid,'SELECT') AS select_access,
        has_table_privilege('academy_runtime',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS other_access,
        has_table_privilege('academy_runtime',c.oid,'SELECT WITH GRANT OPTION') AS select_grant_option
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=c.oid
            AND d.refclassid='pg_extension'::regclass AND d.deptype='e'
        LEFT JOIN pg_extension e ON e.oid=d.refobjid
        WHERE n.nspname <> ALL(:names) AND n.nspname !~ '^pg_'
        AND n.nspname <> 'information_schema' AND c.relkind IN ('r','v','m','p')
        AND has_table_privilege('academy_runtime',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
        ORDER BY n.nspname,c.relname"""), {'names':list(SCHEMAS)}).mappings()]


def inaccessible_statistics_view(row):
    # Observed Supabase baseline: PUBLIC SELECT on these extension-owned views,
    # but no schema USAGE. This is NOT permission to access statistics. Require
    # extension membership, not just a familiar name, and reject any wider ACL.
    return (row['schema'] == 'extensions' and row['kind'] == 'v'
        and row['object'] in ('pg_stat_statements','pg_stat_statements_info')
        and row['extension'] == 'pg_stat_statements'
        and row['select_access'] and not row['schema_usage']
        and not row['other_access'] and not row['select_grant_option'])


def check_role(connection, *, actual_login=False):
    row = connection.exec_driver_sql("""SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreaterole,
        rolcreatedb,rolinherit,rolreplication FROM pg_roles WHERE rolname='academy_runtime'""").one()
    require(row.rolcanlogin and not any(row[1:]), 'RUNTIME_ROLE_UNSAFE')
    require(not connection.exec_driver_sql("""SELECT EXISTS(SELECT FROM pg_auth_members
        WHERE member=(SELECT oid FROM pg_roles WHERE rolname='academy_runtime'))""").scalar_one(), 'RUNTIME_MEMBERSHIP_UNSAFE')
    require(not connection.exec_driver_sql("""SELECT EXISTS(SELECT FROM pg_class
        WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname='academy_runtime'))
        OR EXISTS(SELECT FROM pg_namespace WHERE nspowner=(SELECT oid FROM pg_roles WHERE rolname='academy_runtime'))""").scalar_one(), 'RUNTIME_MUST_NOT_OWN_OBJECTS')
    if actual_login:
        require(connection.exec_driver_sql("SELECT current_user='academy_runtime' AND session_user='academy_runtime'").scalar_one(), 'ACTUAL_RUNTIME_LOGIN_REQUIRED')
        require(connection.exec_driver_sql('SHOW row_security').scalar_one() == 'on', 'ROW_SECURITY_DISABLED')
    # PUBLIC grants are effective for every login. Do not change other schemas to
    # fix them silently; stop and review if they allow runtime to create objects.
    unsafe = connection.exec_driver_sql("""SELECT EXISTS(SELECT FROM pg_namespace WHERE
        nspname !~ '^pg_' AND nspname <> 'information_schema'
        AND has_schema_privilege('academy_runtime',oid,'CREATE'))""").scalar_one()
    require(not unsafe, 'RUNTIME_SCHEMA_CREATE_ACCESS')
    for name in SCHEMAS:
        require(connection.execute(sa.text("SELECT has_schema_privilege('academy_runtime',:name,'USAGE')"), {'name':name}).scalar_one(), 'RUNTIME_SCHEMA_USAGE_MISSING')
    tables = connection.execute(sa.text("""SELECT c.oid,n.nspname,c.relkind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(:names)
        AND c.relkind IN ('r','S')"""), {'names':list(SCHEMAS)}).fetchall()
    require(sum(row.relkind == 'r' for row in tables) == 26, 'PRODUCTION_TABLE_SET_CHANGED')
    for oid, schema, kind in tables:
        privileges = ('USAGE','SELECT') if kind == 'S' else (
            ('SELECT',) if schema == 'academy_migrations' else ('SELECT','INSERT','UPDATE','DELETE'))
        function = 'has_sequence_privilege' if kind == 'S' else 'has_table_privilege'
        for privilege in privileges:
            require(connection.execute(sa.text(f"SELECT {function}('academy_runtime',:oid,:priv)"), {'oid':oid,'priv':privilege}).scalar_one(), 'RUNTIME_REQUIRED_GRANT_MISSING')
        denied = ('UPDATE',) if kind == 'S' else (('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')
                    if schema == 'academy_migrations' else ('TRUNCATE','REFERENCES','TRIGGER'))
        for privilege in denied:
            require(not connection.execute(sa.text(f"SELECT {function}('academy_runtime',:oid,:priv)"), {'oid':oid,'priv':privilege}).scalar_one(), 'RUNTIME_EXCESS_GRANT')
    outside = outside_table_access(connection)
    if any(not inaccessible_statistics_view(row) for row in outside):
        raise RuntimeFailure('RUNTIME_OUTSIDE_TABLE_ACCESS',outside_access=outside)
    return outside


def create_role(connection, password):
    require(not role_exists(connection), 'RUNTIME_EXISTS_NO_OVERWRITE')
    require(isinstance(password,str) and len(password) >= 32, 'RUNTIME_PASSWORD_TOO_SHORT')
    driver = connection.connection.driver_connection
    # libpq hashes locally; neither SQLAlchemy nor the server receives a
    # plaintext password in SQL. Never log even the verifier or composed SQL.
    verifier = driver.pgconn.encrypt_password(password.encode(), ROLE.encode(), b'scram-sha-256').decode()
    with driver.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE ROLE academy_runtime LOGIN NOINHERIT PASSWORD {}').format(sql.Literal(verifier)))
    connection.exec_driver_sql('GRANT USAGE ON SCHEMA academy, academy_auth, academy_migrations TO academy_runtime')
    connection.exec_driver_sql('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA academy, academy_auth TO academy_runtime')
    connection.exec_driver_sql('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA academy TO academy_runtime')
    connection.exec_driver_sql('GRANT SELECT ON ALL TABLES IN SCHEMA academy_migrations TO academy_runtime')
    check_role(connection)


def verify_data(connection, prepared):
    set_owner(connection, prepared['user_id'])
    counts = verify_profile(connection, prepared['user_id'], prepared['profile'])
    require(connection.exec_driver_sql('SELECT count(*) FROM academy_auth.users').scalar_one() == 1, 'UNEXPECTED_OWNER_COUNT')
    require(connection.exec_driver_sql('SELECT realm FROM academy_auth.meta WHERE id=1').scalar_one() == prepared['realm'], 'REALM_CHANGED')
    for table in ('sessions','auth_limits'):
        require(connection.exec_driver_sql(f'SELECT count(*) FROM academy_auth.{table}').scalar_one() == 0, 'UNEXPECTED_ACTIVE_SESSIONS')
    require(connection.exec_driver_sql("SELECT version_num FROM academy_migrations.alembic_version").scalar_one() == 'cloud_0001', 'REVISION_CHANGED')
    require(connection.exec_driver_sql("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='academy' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity""").scalar_one() == 21, 'RLS_CHANGED')
    connection.execution_options(schema_translate_map={None:'academy'})
    try:
        with Session(bind=connection, info={'account':{'id':prepared['user_id']}}, join_transaction_mode='create_savepoint') as session:
            require(dashboard(session)['total_xp'] == 40, 'EXPECTED_40_XP_MISMATCH')
    finally:
        connection.execution_options(schema_translate_map=None)
    return {'total_xp':40,'tables_compared':len(counts),'all_typed_values_match':True}


def runtime_trial(connection, prepared):
    """Caller MUST roll back the whole transaction, including on success."""
    inaccessible = check_role(connection, actual_login=True)
    for row in inaccessible:
        # Never fetch extension contents or query text. A fresh restricted
        # session must reject even name resolution of the view (SQLSTATE 42501).
        quote = connection.dialect.identifier_preparer.quote
        target = quote(row['schema'])+'.'+quote(row['object'])
        try:
            with connection.begin_nested():
                connection.exec_driver_sql(f'SELECT 1 FROM {target} LIMIT 0')
        except sa.exc.DBAPIError as error:
            require(getattr(error.orig,'sqlstate',None) == '42501','SYSTEM_VIEW_WRONG_ERROR')
        else:
            raise RuntimeFailure('SYSTEM_VIEW_ACCESS_NOT_DENIED')
    for owner in ('',str(uuid4())):
        connection.execute(sa.text("SELECT set_config('app.user_id',:id,true)"), {'id':owner})
        for name in prepared['profile']:
            require(connection.exec_driver_sql(f'SELECT count(*) FROM academy."{name}"').scalar_one() == 0, 'RLS_OTHER_OWNER_VISIBLE')
    # Wrong owner insertion must fail with the RLS permission code. Explicit
    # keys avoid nontransactional sequence advancement, even on rejection.
    try:
        with connection.begin_nested():
            connection.execute(sa.text('INSERT INTO academy.planweek(user_id,week_start,revision,created_at) VALUES (:owner,DATE \'2099-01-05\',0,now())'), {'owner':prepared['user_id']})
    except sa.exc.DBAPIError as error:
        require(getattr(error.orig,'sqlstate',None) == '42501', 'RLS_WRITE_WRONG_ERROR')
    else:
        raise RuntimeFailure('RLS_WRITE_NOT_REJECTED')
    result = verify_data(connection, prepared)
    marker = 'runtime-check-'+uuid4().hex
    connection.execute(sa.text('INSERT INTO academy_auth.auth_limits(bucket,started,count) VALUES (:key,0,1)'), {'key':marker})
    require(connection.execute(sa.text('SELECT count FROM academy_auth.auth_limits WHERE bucket=:key'), {'key':marker}).scalar_one() == 1, 'TRANSACTION_WRITE_FAILED')
    return {**result,'actual_runtime_login':True,'rls_other_owner_hidden':True,'rls_write_rejected':True,
        'inaccessible_system_views':[row['schema']+'.'+row['object'] for row in inaccessible],
        'system_view_denials_verified':len(inaccessible)}, marker


def execute(ca_file, credentials, runtime_password, *, create=False, progress=lambda value: None):
    logging.disable(logging.CRITICAL)
    report = {'status':'not_started','supabase_confirmed':False}
    phase = 'LOCAL_BACKUP'
    commit_started = commit_returned = False
    prepared = None
    runtime_url = None
    def step(value):
        nonlocal phase
        phase = value
        progress(value)
    try:
        prepared = transfer.prepare_snapshot()
        step('CONFIGURATION')
        uri, admin_password = credentials
        url = database_url(validate_visible_uri(uri), admin_password, ca_file)
        transfer.validate_project(url, prepared['realm'])
        require(url.username.split('.')[0] == 'postgres', 'EXPECTED_ADMIN_IDENTITY')
        runtime = url.set(username=ROLE+'.'+url.username.rsplit('.',1)[1], password=runtime_password)
        with ExitStack() as resources:
            ca = resources.enter_context(driver_certificate(url.query['sslrootcert']))
            def engine_for(selected):
                def connect():
                    conn = psycopg.connect(host=selected.host,port=5432,dbname=selected.database,user=selected.username,
                        password=selected.password,sslmode='verify-full',sslrootcert=ca,
                        ssl_min_protocol_version='TLSv1.2',gssencmode='disable',options='',connect_timeout=15,
                        prepare_threshold=None,application_name='academy-runtime-setup')
                    if not conn.pgconn.ssl_in_use:
                        conn.close()
                        raise RuntimeFailure('TLS_REQUIRED')
                    return conn
                engine = sa.create_engine('postgresql+psycopg://',creator=connect,poolclass=sa.pool.NullPool,hide_parameters=True)
                resources.callback(engine.dispose)
                return engine
            admin = engine_for(url)
            step('READ_ONLY_PREFLIGHT')
            with admin.connect() as connection:
                with connection.begin():
                    connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                    connection.exec_driver_sql("SET LOCAL statement_timeout='60s'")
                    require(not role_exists(connection),'RUNTIME_EXISTS_NO_OVERWRITE')
                    transfer.verify_import(connection,prepared)
                    baseline = external_permissions(connection)
                if not create:
                    report = {'status':'inspection_passed','mode':'read_only','runtime_absent':True,'total_xp':40}
                else:
                    step('CREATE_RESTRICTED_LOGIN')
                    with connection.begin() as transaction:
                        connection.exec_driver_sql("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='60s'")
                        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtextextended('academy-runtime-setup',0))")
                        transfer.verify_import(connection,prepared)
                        create_role(connection,runtime_password)
                        require(external_permissions(connection) == baseline,'OUTSIDE_PERMISSIONS_CHANGED')
                        transfer.assert_source_unchanged(prepared)
                        step('COMMIT')
                        commit_started = True
                        transaction.commit()
                        commit_returned = True
                    # Keep URL only in GUI memory, including if verification later
                    # fails. An existing login is never reset or recreated blindly.
                    runtime_url = runtime.set(query={'sslmode':'verify-full','sslrootcert':'/etc/secrets/supabase-ca.pem'}).render_as_string(hide_password=False)
                    step('VERIFY_ACTUAL_LOGIN')
                    live = engine_for(runtime)
                    with live.connect() as restricted:
                        transaction = restricted.begin()
                        try:
                            restricted.exec_driver_sql("SET LOCAL statement_timeout='60s'")
                            details,marker = runtime_trial(restricted,prepared)
                        finally:
                            transaction.rollback()
                        with restricted.begin():
                            restricted.exec_driver_sql('SET TRANSACTION READ ONLY')
                            require(restricted.execute(sa.text('SELECT count(*) FROM academy_auth.auth_limits WHERE bucket=:key'), {'key':marker}).scalar_one() == 0,'ROLLBACK_NOT_VERIFIED')
                            require(not restricted.exec_driver_sql("SELECT COALESCE(current_setting('app.user_id',true),'')").scalar_one(),'OWNER_CONTEXT_LEAK')
                            verify_data(restricted,prepared)
                    with connection.begin():
                        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                        verify_data(connection,prepared)
                        require(external_permissions(connection) == baseline,'OUTSIDE_PERMISSIONS_CHANGED')
                    transfer.assert_source_unchanged(prepared)
                    report = {'status':'passed','supabase_confirmed':True,'commit_verified':True,
                        'tls':'verify-full','role':ROLE,'rollback_verified':True,'source_unchanged':True,
                        'outside_permissions_unchanged':True,'creator_set_granted':False,**details}
    except (RuntimeFailure,transfer.TransferFailure) as error:
        report['error'] = str(error)
        if getattr(error,'outside_access',None) is not None:
            report['outside_access'] = error.outside_access
    except ConfigurationError:
        report['error'] = 'CONFIGURATION_REVIEW_INPUT'
    except Exception as error:
        report['diagnostic'] = safe_diagnostic(error,phase)
        report['error'] = report['diagnostic']['code']
    if report['status'] == 'not_started':
        report.update(status=('committed_verification_failed_do_not_retry' if commit_returned else
            'commit_unconfirmed_do_not_retry' if commit_started else 'failed_no_commit_requested'),phase=phase)
    if prepared:
        report['backup_folder'] = str(prepared['folder'].relative_to(ROOT))
    directory = ROOT/'.test-artifacts'
    directory.mkdir(exist_ok=True)
    path = directory/('runtime-setup-result.json' if create else 'runtime-setup-inspection.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report,runtime_url
