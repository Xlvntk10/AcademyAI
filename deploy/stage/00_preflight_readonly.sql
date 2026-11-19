-- Read-only preflight; no credentials, personal records or modifications.
BEGIN READ ONLY;
SELECT current_setting('server_version') AS postgres_version,
       current_setting('ssl') AS server_ssl,
       COALESCE((SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()), false) AS connection_ssl;
SELECT rolcreaterole, rolcreatedb, rolsuper, rolbypassrls
FROM pg_roles WHERE rolname = current_user;
SELECT has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_schema;
SELECT nspname AS existing_stage_schema FROM pg_namespace
WHERE nspname IN ('academy_stage', 'academy_stage_auth', 'academy_stage_migrations');
SELECT rolname AS existing_stage_role FROM pg_roles WHERE rolname='academy_stage_runtime';
-- Empty last two result sets are required. Existing objects must be reviewed, never overwritten.
-- Client-side verify-full is required independently; server_ssl alone cannot prove it.
ROLLBACK;
