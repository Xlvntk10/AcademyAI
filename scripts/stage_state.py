"""Read-only PostgreSQL catalog inspection; never imports or invokes migrations."""
import sqlalchemy as sa

SCHEMAS = ('academy_stage', 'academy_stage_auth', 'academy_stage_migrations')


def inspect_stage(connection):
    if connection.exec_driver_sql('SHOW transaction_read_only').scalar_one() != 'on':
        raise RuntimeError('READ_ONLY_REQUIRED')
    own = connection.exec_driver_sql("""SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,
        has_database_privilege(current_user,current_database(),'CREATE') AS can_create_schema
        FROM pg_roles WHERE rolname=current_user""").mappings().one()
    schema_rows = connection.execute(sa.text("""SELECT n.nspname,
        has_schema_privilege(current_user,n.oid,'USAGE') AS can_use,
        count(c.oid) FILTER (WHERE c.relkind IN ('r','p')) AS tables,
        count(c.oid) FILTER (WHERE c.relkind='S') AS sequences,
        count(c.oid) FILTER (WHERE c.relkind IN ('i','I')) AS indexes,
        count(c.oid) FILTER (WHERE c.relkind IN ('r','p') AND c.relrowsecurity AND c.relforcerowsecurity) AS force_rls_tables
        FROM pg_namespace n LEFT JOIN pg_class c ON c.relnamespace=n.oid
        WHERE n.nspname=ANY(:schemas) GROUP BY n.nspname,n.oid ORDER BY n.nspname"""), {'schemas':list(SCHEMAS)}).mappings().all()
    schemas = {name:{'exists':False} for name in SCHEMAS}
    for row in schema_rows:
        schemas[row['nspname']] = {'exists':True, **{k:v for k,v in row.items() if k != 'nspname'}}
    role = connection.exec_driver_sql("""SELECT rolcanlogin,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolinherit,
        CASE WHEN current_setting('server_version_num')::int >= 160000
             THEN pg_has_role(current_user,oid,'SET') ELSE pg_has_role(current_user,oid,'MEMBER') END AS can_set_role
        FROM pg_roles WHERE rolname='academy_stage_runtime'""").mappings().first()
    # No rows from learning, Auth/session, public or storage tables are read.
    result = {'schemas':schemas, 'runtime_role':{'exists':role is not None, **(dict(role) if role else {})},
              'connected_role_privileges':dict(own), 'transaction_read_only':True,
              'personal_rows_read':False, 'data_rows':'not_inspected',
              'state':'absent' if not schema_rows and role is None else 'objects_present_review_required'}
    result['previous_attempt_origin'] = 'cannot_determine_from_catalog'
    return result
