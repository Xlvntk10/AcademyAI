# Restricted runtime access — verified result

Status: production `academy_runtime` created and verified on 19 November 2026.
The real session-pooler login succeeded with verify-full TLS and the committed
configuration was checked. All 21 tables match the preserved source, including
40 XP. Another owner's rows are hidden, the wrong-owner write is rejected, and
the synthetic transaction marker is absent after rollback. Both inaccessible
statistics views were probed and refused access. Outside permissions and the
local source are unchanged. No extra creator SET grant was made.

The private recovery snapshot is in `backups/production-20261119T051522600029Z`.
The safe execution evidence is `.test-artifacts/runtime-setup-result.json`.
Do not run creation again: the helper deliberately refuses an existing role.
Validation: final full backend suite, **222 passed**, 19 November 2026. One existing
Starlette/httpx deprecation warning. Frontend was unchanged and was not rerun.
Stage and the separately authorized 40 XP production snapshot import are already
complete. Do not rerun those migrations/imports.

## Observed setup refusal and correction

The first real creation attempt stopped before COMMIT with
`RUNTIME_OUTSIDE_TABLE_ACCESS`. A subsequent read-only inspection confirmed the
role is absent, all 21 imported tables match, 40 XP remain, the production ACLs
remain owner-only, and the local source is unchanged.

The only outside PUBLIC table grants found were SELECT on
`extensions.pg_stat_statements` and `extensions.pg_stat_statements_info`, both
views owned by the pg_stat_statements extension. PUBLIC has no USAGE on their
schema. The original guard incorrectly treated those table ACLs alone as access.

The correction accepts only those exact extension-member views with SELECT only,
no grant option and no runtime schema USAGE. Any other outside grant still stops
setup. Actual runtime verification additionally requires each zero-row probe to
fail with SQLSTATE 42501. No extension/schema ACL is changed. Tests use the real
local pg_stat_statements extension and also reject a lookalike view, schema USAGE,
write rights and grant options. Fresh runtime authentication is essential; no
previously privileged session is reused.

Correction validation: 28 runtime/transfer tests passed, including the real local
extension and all six new compatibility/security cases. The corrected form has
now completed production creation and its separate authenticated verification.

PostgreSQL documents the independent schema lookup requirement under
[USAGE](https://www.postgresql.org/docs/17/ddl-priv.html). This correction does not
assert isolation from arbitrary SECURITY DEFINER functions or a compromised
trusted backend; it verifies the documented direct table-access boundary.

`python -m scripts.runtime_desktop` opens a local form with clipboard buttons.
It generates a separate random runtime password. The owner must save that password
outside chat before clicking the creation button. The form never saves credentials
or DATABASE_URL in a file. The administrator password is cleared from its field
before the worker starts. The completed connection string is copied only by the
owner's explicit button press, for Render's backend DATABASE_URL.

The executor:

- makes fresh verified local backups and selects the actual 40 XP profile;
- verifies TLS with hostname and CA checks, binds the pooler project to the local
  account realm, and compares the imported typed data before changing permissions;
- refuses to overwrite an existing `academy_runtime`;
- creates a LOGIN with NOINHERIT and default unprivileged attributes; hashes the
  new password locally with libpq SCRAM-SHA-256 before composing the SQL;
- grants only schema USAGE, table SELECT/INSERT/UPDATE/DELETE for academy and
  academy_auth, sequence USAGE/SELECT, and read-only migration metadata;
- rejects role membership, elevated attributes, object ownership, schema CREATE,
  excessive table/sequence permissions, and access to other application tables;
- checks existing outside ACLs, roles, memberships, functions' ACLs and row policies;
- commits the role and grants together, then authenticates in a separate connection
  as the real runtime session/current user; no extra creator SET grant is needed;
- checks 21 tables with missing and foreign owner context, an RLS-rejected write,
  the complete typed 40 XP profile, and a synthetic rate-limit marker rolled back
  in full. The synthetic trial does not advance sequences or change profile rows;
- checks the marker is absent, transaction owner context was cleared, and source
  files and outside permissions remain unchanged.

A role cannot be authenticated from a separate connection before it is committed.
If commit is uncertain, or postcommit authentication/verification fails, the report
explicitly says so and the form stops. It does not reset a password, drop a role,
rerun migrations, or claim a rollback after commit.

Local tests exercise role/grant rollback, RLS with both session_user and current_user
restricted, wrong-owner visibility and insertion, excessive privileges, existing-role
refusal, and a nonsuperuser creator with the PostgreSQL 16+ default empty
createrole_self_grant. Production authentication is evidence only after the real
form has succeeded; local SET SESSION AUTHORIZATION is not reported as a real
pooler login.

The backend remains trusted to select an authenticated owner context and to handle
academy_auth sessions. RLS does not protect against a compromised backend that has
the runtime credentials and can choose another owner context.

Render form currently has a draft API service using Docker, Frankfurt and Free.
Only main is available remotely. The 41 outgoing commits through df465b6 were
scanned as 424 blobs (3,741,141 bytes) for fixed secret patterns and sensitive file
names. Three URI matches were reviewed: historical versions of the local TLS test
in tests/test_deployment.py, all targeting 127.0.0.1/test. A pattern scan is not a
guarantee that arbitrary secrets cannot exist.

No push, public deployment, paid operation, or runtime credentials sent to Render
has occurred. Public push/deployment still need the owner's explicit confirmation.
