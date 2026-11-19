"""Apply the approved empty stage and run rollback-only tests. Never migrate production.

Use an interactive local terminal. Credentials are held only in process memory.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import logging
from pathlib import Path
import sys
import getpass
import sqlalchemy as sa
import psycopg
from scripts.check_postgres import (visible_uri, hidden, database_url, driver_certificate,
                                    ConfigurationError, diagnose)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ('academy_stage', 'academy_stage_auth', 'academy_stage_migrations')
PINNED = {'00_preflight_readonly.sql': '90f4cab0540cde3c982d9f68b2000de1516f1d08cb94121c1350675434ce710c', '01_schema.sql': 'e7a3255440f2e5171a4e3b13a09be7c8c103ce20ee8ced57730161de22b598dc', '02_smoke_rollback.sql': '80a7bbb660b8b17171e45ae11714937adfa7b1b11b67747a355728100a3e72c8'}  # Filled from reviewed SQL; changed SQL fails closed.


class StageFailure(RuntimeError):
    pass


def reviewed_sql():
    result = {}
    for name, expected in PINNED.items():
        content = (ROOT/'deploy/stage'/name).read_text(encoding='utf-8-sig')
        if hashlib.sha256(content.encode('utf8')).hexdigest() != expected:
            raise StageFailure('PLAN_CHANGED')
        result[name] = content
    if set(result) != {'00_preflight_readonly.sql', '01_schema.sql', '02_smoke_rollback.sql'}:
        raise StageFailure('PLAN_MISSING')
    return result


def transaction_body(sql, ending):
    if not sql.rstrip().endswith(ending):
        raise StageFailure('PLAN_TRANSACTION')
    return sql[sql.index('BEGIN;')+len('BEGIN;'):].rstrip().removesuffix(ending)


def catalog_outside_stage(connection):
    return connection.exec_driver_sql("""SELECT n.nspname,c.relname,c.relkind,c.oid
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
        AND n.nspname NOT IN ('academy_stage','academy_stage_auth','academy_stage_migrations')
        ORDER BY n.nspname,c.relname,c.oid""").fetchall()


def apply_and_test(connection, plans):
    """Caller owns the transaction; function never commits schemas itself."""
    from scripts.stage_learning_trial import learning_trial
    outside = catalog_outside_stage(connection)
    occupied = connection.execute(sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = ANY(:names)"), {'names':list(SCHEMAS)}).scalar_one()
    role = connection.exec_driver_sql("SELECT 1 FROM pg_roles WHERE rolname='academy_stage_runtime'").first()
    if occupied or role:
        raise StageFailure('STAGE_ALREADY_EXISTS')
    connection.exec_driver_sql(transaction_body(plans['01_schema.sql'], 'COMMIT;'), execution_options={'no_parameters':True})
    with connection.begin_nested() as smoke:
        connection.exec_driver_sql(transaction_body(plans['02_smoke_rollback.sql'], 'ROLLBACK;'), execution_options={'no_parameters':True})
        smoke.rollback()
    with connection.begin_nested() as learning:
        connection.exec_driver_sql('SET LOCAL ROLE academy_stage_runtime')
        connection.exec_driver_sql('SET LOCAL search_path TO academy_stage, pg_catalog')
        details = learning_trial(connection)
        learning.rollback()
    # Registry has no RLS: zero owners plus enforced owner FKs prove that no
    # tenant rows can remain, even when FORCE RLS hides rows from the DDL owner.
    if connection.exec_driver_sql('SELECT count(*) FROM academy_stage_auth.users').scalar_one() != 0:
        raise StageFailure('TEST_OWNERS_REMAIN')
    inspector = sa.inspect(connection)
    for schema in SCHEMAS[:2]:
        for table in inspector.get_table_names(schema=schema):
            if connection.exec_driver_sql(f'SELECT count(*) FROM "{schema}"."{table}"').scalar_one() != 0:
                raise StageFailure('TEST_ROWS_REMAIN')
    tables = {schema:inspector.get_table_names(schema=schema) for schema in SCHEMAS}
    if [len(tables[s]) for s in SCHEMAS] != [21,4,1]:
        raise StageFailure('TABLE_COUNT')
    if connection.exec_driver_sql('SELECT version_num FROM academy_stage_migrations.alembic_version').scalar_one() != 'cloud_0001':
        raise StageFailure('REVISION')
    flags = connection.exec_driver_sql("SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolinherit FROM pg_roles WHERE rolname='academy_stage_runtime'").one()
    if any(flags):
        raise StageFailure('ROLE_PRIVILEGES')
    if catalog_outside_stage(connection) != outside:
        raise StageFailure('OUTSIDE_CATALOG_CHANGED')
    return {'objects':tables, 'role':'academy_stage_runtime', 'role_login':False,
            'rls_and_foreign_keys':True, 'learning_trial':details,
            'test_rows_after_rollback':0, 'outside_catalog_unchanged':True,
            'remaining_data':'only cloud_0001 in alembic_version; sequences may have advanced'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ca-file', required=True)
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    report = {'status':'not_started', 'supabase_confirmed':False}
    commit_started = False
    engine = None
    try:
        plans = reviewed_sql()  # Check the plan BEFORE asking for credentials.
        uri = visible_uri()
        password = hidden('Пароль PostgreSQL (скрытый ввод): ')
        url = database_url(uri, password, args.ca_file)
        if not url.host.endswith('.pooler.supabase.com'):
            raise StageFailure('SUPABASE_SESSION_POOLER_REQUIRED')
        with ExitStack() as resources:
            ca = resources.enter_context(driver_certificate(url.query['sslrootcert']))
            def connect():
                conn = psycopg.connect(host=url.host, port=5432, dbname=url.database,
                    user=url.username, password=url.password, sslmode='verify-full', sslrootcert=ca,
                    ssl_min_protocol_version='TLSv1.2', gssencmode='disable', options='',
                    application_name='academy-stage-approved', connect_timeout=15, prepare_threshold=None)
                if not conn.pgconn.ssl_in_use:
                    conn.close()
                    raise StageFailure('TLS_REQUIRED')
                return conn
            # No URL with a secret is passed to SQLAlchemy/logging.
            engine = sa.create_engine('postgresql+psycopg://', creator=connect,
                                      poolclass=sa.pool.NullPool, hide_parameters=True)
            with engine.connect() as connection:
                with connection.begin() as transaction:
                    details = apply_and_test(connection, plans)
                    commit_started = True
                    transaction.commit()
                # Confirm the committed result using a new transaction.
                with connection.begin():
                    if connection.exec_driver_sql('SELECT version_num FROM academy_stage_migrations.alembic_version').scalar_one() != 'cloud_0001':
                        raise StageFailure('COMMIT_NOT_CONFIRMED')
            report = {'status':'passed', 'supabase_confirmed':True, 'tls':'verify-full', **details}
            engine.dispose()
            engine = None
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        report['error'] = 'CONFIGURATION'
    except StageFailure as error:
        report['error'] = str(error)  # All messages above are fixed, no driver text.
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        report['error'] = 'INTERACTIVE_INPUT_CANCELLED'
    except Exception as error:
        report['error'] = diagnose(error)  # Only a safe category, never raw exception/URI.
    finally:
        if engine is not None:
            engine.dispose()
    if report['status'] != 'passed':
        report['status'] = 'commit_unconfirmed_do_not_retry_blindly' if commit_started else 'failed_no_commit_requested'
    folder = ROOT/'.test-artifacts'
    folder.mkdir(exist_ok=True)
    (folder/'supabase-stage-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
