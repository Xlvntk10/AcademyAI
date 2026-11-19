"""Read-only role capability checks and explicit RLS test identity assertions."""


def creation_capabilities(connection):
    row = connection.exec_driver_sql("""SELECT current_setting('server_version_num')::int AS version_num,
        current_user = session_user AS same_identity,
        current_setting('createrole_self_grant',true) AS self_grant,
        r.rolsuper,r.rolcreaterole,
        has_database_privilege(current_user,current_database(),'CREATE') AS can_create_schema,
        s.rolsuper AS session_superuser
        FROM pg_roles r JOIN pg_roles s ON s.rolname=session_user
        WHERE r.rolname=current_user""").mappings().one()
    auto_set = 'set' in {part.strip() for part in (row['self_grant'] or '').split(',')}
    return {'server_version_num':row['version_num'], 'same_session_and_current_role':row['same_identity'],
            'can_create_schema':row['can_create_schema'],
            'can_create_role':row['rolsuper'] or row['rolcreaterole'],
            'creator_auto_set':auto_set, 'session_superuser':row['session_superuser'],
            'new_role_set_expected':row['session_superuser'] or (row['same_identity'] and auto_set)}


def restricted_role_evidence(connection):
    # SET ROLE itself is never replaced by an administrator-side RLS check.
    connection.exec_driver_sql('SET LOCAL ROLE academy_stage_runtime')
    row = connection.exec_driver_sql("""SELECT current_user='academy_stage_runtime' AS exact_role,
        rolcanlogin,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolinherit
        FROM pg_roles WHERE rolname=current_user""").mappings().one()
    row_security = connection.exec_driver_sql('SHOW row_security').scalar_one() == 'on'
    if not row['exact_role'] or not row_security or any(v for k,v in row.items() if k != 'exact_role'):
        from scripts.run_stage import StageFailure
        raise StageFailure('RLS_TEST_ROLE_UNSAFE')
    return {'role':'academy_stage_runtime', 'bypassrls':False, 'superuser':False,
            'login':False, 'row_security':True}
