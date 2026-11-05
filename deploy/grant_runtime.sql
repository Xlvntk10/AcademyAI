-- Run as the migration owner after creating academy_runtime with a private password.
-- The runtime role must have no membership in elevated roles.
-- Create a fresh LOGIN role with default unprivileged attributes first.
-- Avoid ALTER ... NOSUPERUSER, which managed Supabase admins cannot execute.
GRANT USAGE ON SCHEMA academy, academy_auth, academy_migrations TO academy_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA academy, academy_auth TO academy_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA academy TO academy_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA academy_migrations TO academy_runtime;
