-- Synthetic stage-only rehearsal. All test rows are rolled back, also on failure.
-- These UUIDs are fixtures, NOT Supabase Auth users. No auth.users insert occurs.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL ROLE academy_stage_runtime;
SET LOCAL search_path = academy_stage, pg_catalog;
DO $smoke$
DECLARE first_id text := '00000000-0000-4000-8000-000000000001';
        second_id text := '00000000-0000-4000-8000-000000000002';
BEGIN
    IF EXISTS (SELECT 1 FROM academy_stage_auth.users) THEN
        RAISE EXCEPTION 'Smoke test requires an empty stage';
    END IF;
    INSERT INTO academy_stage_auth.users(user_id) VALUES (first_id), (second_id);
    PERFORM set_config('app.user_id', first_id, true);
    INSERT INTO skill(id, name, description) VALUES (1, 'Stage English', 'Synthetic fixture');
    INSERT INTO lesson(id, skill_id, title, level) VALUES (1, 1, 'Stage lesson', 'A2');
    PERFORM set_config('app.user_id', second_id, true);
    IF EXISTS (SELECT 1 FROM lesson) THEN RAISE EXCEPTION 'Owner isolation failed'; END IF;
    BEGIN
        INSERT INTO lesson(id, skill_id, title, level) VALUES (1, 1, 'Foreign skill', 'A2');
        RAISE EXCEPTION 'Cross-owner foreign key accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO skill(user_id, id, name, description) VALUES (first_id, 2, 'Forbidden', 'fixture');
        RAISE EXCEPTION 'RLS insert accepted';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='academy_stage' AND c.relkind='r'
        AND c.relrowsecurity AND c.relforcerowsecurity) != 21 THEN
        RAISE EXCEPTION 'Missing FORCE RLS';
    END IF;
    PERFORM set_config('app.user_id', '', true);
    IF EXISTS (SELECT 1 FROM skill) THEN RAISE EXCEPTION 'Anonymous access accepted'; END IF;
END
$smoke$;
ROLLBACK;
