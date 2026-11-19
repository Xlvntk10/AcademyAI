"""Exercise existing grading/replay services in stage, inside an outer transaction.

No HTTP server, Auth provider, personal SQLite, or production schema is used.
"""
from datetime import timedelta
from uuid import uuid4
import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session
from app.database.cloud import empty_profile
from app.database.models import LessonRun
from app.offline_schemas import OfflineSubmission, OfflineAcknowledgement
from app.routers.offline import download, sync_attempt
from app.services.analytics import dashboard
from app.services import clock

OWNERS = ('00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002')


def learning_trial(connection):
    """Caller rolls back the savepoint, including commits made by sync_attempt."""
    profile = empty_profile()  # Authored seed in temporary SQLite; never a user file.
    metadata = sa.MetaData(schema='academy_stage')
    metadata.reflect(connection, schema='academy_stage')
    tables = [table for table in metadata.sorted_tables if table.schema == 'academy_stage']
    if set(profile) != {table.name for table in tables}:
        raise RuntimeError('STAGE_SCHEMA_MISMATCH')
    for owner in OWNERS:
        connection.execute(sa.text('INSERT INTO academy_stage_auth.users(user_id) VALUES (:id)'), {'id':owner})
        connection.execute(sa.text("SELECT set_config('app.user_id', :id, true)"), {'id':owner})
        for table in tables:
            rows = [{**row, 'user_id':owner} for row in profile[table.name]]
            if table.name == 'syncidentity':
                rows = [{'id':1, 'server_id':str(uuid4()), 'user_id':owner}]
            if rows:
                connection.execute(table.insert(), rows)

    # Only this maintenance connection gets a translated ORM schema and search path.
    # Do not change global SQLModel metadata or the application's account hooks.
    def stage_path(conn, cursor, statement, parameters, context, executemany):
        if statement == 'SET LOCAL search_path TO academy, public':
            statement = 'SET LOCAL search_path TO academy_stage, pg_catalog'
        return statement, parameters

    sa.event.listen(connection, 'before_cursor_execute', stage_path, retval=True)
    connection.execution_options(schema_translate_map={None:'academy_stage'})
    try:
        def session(owner):
            return Session(bind=connection, info={'account':{'id':owner}}, join_transaction_mode='create_savepoint')
        with session(OWNERS[0]) as first:
            bundle = download('a2-daily-routine', first)
            answers = {row['id']:row['correct_answer'] for row in profile['exercise']}
            now = clock.now()
            payload = OfflineSubmission.model_validate(dict(protocol=1, attempt_id=str(uuid4()),
                server_id=bundle['server_id'], lesson_slug='a2-daily-routine',
                content_version=bundle['lesson']['version'], content_hash=bundle['content_hash'],
                started_at=now-timedelta(minutes=15), completed_at=now-timedelta(minutes=1),
                answers=[dict(exercise_id=e['id'], answer=answers[e['id']]) for e in bundle['lesson']['exercises']]))
            accepted = OfflineAcknowledgement.model_validate(sync_attempt(payload, first)).model_dump(mode='json')
            if dashboard(first)['total_xp'] != 60:
                raise RuntimeError('STAGE_XP_MISMATCH')
        # Independent ORM session on the same transaction, simulating a second client.
        with session(OWNERS[0]) as second:
            replay = OfflineAcknowledgement.model_validate(sync_attempt(payload, second)).model_dump(mode='json')
            if replay != accepted or dashboard(second)['total_xp'] != 60:
                raise RuntimeError('STAGE_REPLAY_MISMATCH')
            changed = payload.model_copy(deep=True)
            changed.answers[0].answer = 'study'
            try:
                sync_attempt(changed, second)
            except HTTPException as error:
                if error.status_code != 409:
                    raise RuntimeError('STAGE_CONFLICT_STATUS') from None
            else:
                raise RuntimeError('STAGE_CONFLICT_ACCEPTED')
        with session(OWNERS[1]) as outsider:
            if dashboard(outsider)['total_xp'] != 0 or outsider.get(LessonRun, str(payload.attempt_id)) is not None:
                raise RuntimeError('STAGE_OWNER_LEAK')
            try:
                sync_attempt(payload, outsider)
            except HTTPException as error:
                if error.status_code != 409:
                    raise RuntimeError('STAGE_FOREIGN_RECEIPT_STATUS') from None
            else:
                raise RuntimeError('STAGE_FOREIGN_RECEIPT_ACCEPTED')
        return {'server_grading':True, 'synthetic_xp':60, 'replayed_xp':60,
                'other_account_xp':0, 'conflict_rejected':True,
                'scope':'existing service functions; independent sessions, not HTTP or real devices'}
    finally:
        connection.execution_options(schema_translate_map=None)
        sa.event.remove(connection, 'before_cursor_execute', stage_path)
