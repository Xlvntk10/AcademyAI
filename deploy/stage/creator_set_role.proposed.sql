-- PROPOSAL ONLY. Not loaded or executed by scripts.run_stage.
-- Requires separate user approval for this additional SET permission.
-- PostgreSQL 16+. Insert immediately AFTER creating academy_stage_runtime,
-- inside the SAME creation transaction, BEFORE running RLS tests.
-- CURRENT_USER must equal SESSION_USER, the verified schema/role creator.
-- Grants the creator the ability to assume the NEW restricted stage role.
-- Never grant an administrative role TO academy_stage_runtime (wrong direction).
-- No LOGIN, BYPASSRLS, SUPERUSER, or access to other schemas is added to stage.
GRANT academy_stage_runtime TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;
