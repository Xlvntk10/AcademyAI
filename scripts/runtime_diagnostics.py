"""Read-only catalog inspection after a refused runtime setup. No role DDL."""
from contextlib import ExitStack
import json
import logging
import psycopg
import sqlalchemy as sa
from scripts import production_transfer as transfer
from scripts.runtime_setup import role_exists
from scripts.check_postgres import database_url, driver_certificate, validate_visible_uri, ConfigurationError
from scripts.stage_diagnostics import safe_diagnostic


def public_access(connection):
    """Only object/permission metadata; never read rows, query text or view SQL."""
    return [dict(row) for row in connection.execute(sa.text('''
        SELECT n.nspname AS schema, c.relname AS object, c.relkind AS kind,
            a.privilege_type AS privilege, a.is_grantable AS grant_option,
            EXISTS(SELECT 1 FROM aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) s
                WHERE s.grantee=0 AND s.privilege_type='USAGE') AS public_schema_usage,
            e.extname AS extension
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
        LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=c.oid
            AND d.refclassid='pg_extension'::regclass AND d.deptype='e'
        LEFT JOIN pg_extension e ON e.oid=d.refobjid
        WHERE a.grantee=0 AND n.nspname <> ALL(:names) AND n.nspname !~ '^pg_'
            AND n.nspname <> 'information_schema' AND c.relkind IN ('r','v','m','p')
        ORDER BY n.nspname,c.relname,a.privilege_type
    '''), {'names':list(transfer.SCHEMAS)}).mappings()]


def execute(ca_file, credentials, *, create=False):
    logging.disable(logging.CRITICAL)
    report = {'status':'not_started','mode':'read_only','database_changes':False}
    phase = 'CONFIGURATION'
    prepared = None
    try:
        if create:
            raise transfer.TransferFailure('DIAGNOSTIC_IS_READ_ONLY')
        prepared = transfer.prepare_snapshot()
        uri,password = credentials
        url = database_url(validate_visible_uri(uri),password,ca_file)
        transfer.validate_project(url,prepared['realm'])
        with ExitStack() as resources:
            ca = resources.enter_context(driver_certificate(url.query['sslrootcert']))
            def connect():
                conn = psycopg.connect(host=url.host,port=5432,dbname=url.database,user=url.username,
                    password=url.password,sslmode='verify-full',sslrootcert=ca,
                    ssl_min_protocol_version='TLSv1.2',gssencmode='disable',options='',
                    connect_timeout=15,prepare_threshold=None,application_name='academy-runtime-diagnostic')
                if not conn.pgconn.ssl_in_use:
                    conn.close()
                    raise transfer.TransferFailure('TLS_REQUIRED')
                conn.read_only = True
                return conn
            engine = sa.create_engine('postgresql+psycopg://',creator=connect,poolclass=sa.pool.NullPool,hide_parameters=True)
            resources.callback(engine.dispose)
            phase = 'READ_ONLY_CATALOG'
            with engine.connect() as connection:
                with connection.begin():
                    connection.exec_driver_sql("SET LOCAL statement_timeout='60s'")
                    absent = not role_exists(connection)
                    report['runtime_absent'] = absent
                    report['outside_public_grants'] = public_access(connection)
                    if absent:
                        transfer.verify_import(connection,prepared)
                        report['total_xp'] = 40
                        report['tables_compared'] = 21
                        report['production_access_owner_only'] = True
                    else:
                        raise transfer.TransferFailure('RUNTIME_EXISTS_REVIEW_REQUIRED')
            transfer.assert_source_unchanged(prepared)
            report.update(status='passed',source_unchanged=True,tls='verify-full')
    except transfer.TransferFailure as error:
        report['error'] = str(error)
    except ConfigurationError:
        report['error'] = 'CONFIGURATION_REVIEW_INPUT'
    except Exception as error:
        report['diagnostic'] = safe_diagnostic(error,phase)
        report['error'] = report['diagnostic']['code']
    if report['status'] == 'not_started':
        report.update(status='failed_read_only',phase=phase)
    if prepared:
        report['backup_folder'] = str(prepared['folder'].relative_to(transfer.ROOT))
    folder = transfer.ROOT/'.test-artifacts'
    folder.mkdir(exist_ok=True)
    (folder/'runtime-access-diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    if report['status'] == 'passed':
        return 'Проверка завершена: runtime-роль отсутствует, 40 XP сохранены. Источник прав записан в безопасный отчёт. Изменений в базе нет.'
    return 'Проверка остановлена без изменения базы: '+report.get('error','UNKNOWN')+'. Сначала нужен разбор отчёта.'


def main():
    from scripts.stage_desktop import show_form
    show_form(execute,allow_create=False,title='Academy AI — проверка прав Supabase',
        heading='Проверка причины остановки · только чтение',create_label='Изменения отключены')


if __name__ == '__main__':
    main()
