import sqlite3
import pytest
from alembic import command
from alembic.config import Config
from scripts.prepare_db import migrate, prepare, snapshot, verify, assert_preserved, ROOT


def legacy_db(path):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = "sqlite:///" + path.as_posix()
    command.upgrade(cfg, "0001_legacy")
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO skill VALUES (100, 'Reading', 'original skill')")
        db.execute("INSERT INTO lesson VALUES (100,100,'Original lesson','A2')")
        db.execute("INSERT INTO exercise VALUES (100,100,'Original question','answer',10)")
        db.execute("INSERT INTO attempt VALUES (100,100,'my answer',0,0,'2026-10-29 06:19:30.145191')")
        db.execute("DROP TABLE alembic_version")


def test_unversioned_legacy_database_preserved_and_upgrade_repeatable(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_db(path)
    before = snapshot(path)
    prepare(path, tmp_path / "backups")
    assert_preserved(before, path)
    assert len(list((tmp_path / "backups").glob("*.db"))) == 2
    first = snapshot(path)
    migrate(path)
    assert snapshot(path) == first
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM lessoncontent").fetchone()[0] == 20
        assert db.execute("SELECT count(*) FROM exercisecontent").fetchone()[0] == 120
        assert db.execute("SELECT count(*) FROM attempt").fetchone()[0] == 1
    verify(path)


def test_unknown_schema_is_rejected_without_partial_migration(tmp_path):
    path = tmp_path / "unexpected.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE personal_notes (id INTEGER PRIMARY KEY, body TEXT)")
        db.execute("INSERT INTO personal_notes VALUES (1, 'keep this')")
    with pytest.raises(RuntimeError, match="Unexpected legacy tables"):
        migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM personal_notes").fetchall() == [(1, "keep this")]
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("personal_notes",)]


def test_legacy_demo_attempts_are_not_counted_as_progress(tmp_path):
    from fastapi.testclient import TestClient
    from app.database.db import make_engine
    from app.main import create_app
    path = tmp_path / "legacy.db"
    legacy_db(path)
    migrate(path)
    engine = make_engine("sqlite:///" + path.as_posix())
    with TestClient(create_app(engine)) as client:
        result = client.get("/api/progress").json()
        assert result["total_xp"] == 0
        assert result["completed_runs"] == 0
        assert result["completed_lessons"] == 0
    engine.dispose()


def test_vocabulary_upgrade_preserves_existing_learning_and_planner_rows(tmp_path):
    path = tmp_path / 'v4.db'
    cfg = Config(str(ROOT / 'alembic.ini'))
    cfg.attributes['database_url'] = 'sqlite:///' + path.as_posix()
    command.upgrade(cfg, '0004_academies')
    with sqlite3.connect(path) as db:
        lesson_id = db.execute('SELECT lesson_id FROM lessoncontent ORDER BY lesson_id LIMIT 1').fetchone()[0]
        exercise_id = db.execute('SELECT id FROM exercise WHERE lesson_id=? ORDER BY id LIMIT 1', (lesson_id,)).fetchone()[0]
        db.execute("INSERT INTO lessonrun VALUES ('old-run', ?, 1, '2026-11-02 07:00:00', NULL)", (lesson_id,))
        attempt_id = db.execute("INSERT INTO attempt (exercise_id,answer,is_correct,earned_points,created_at) VALUES (?, 'my old answer', 0, 0, '2026-11-02 07:01:00')", (exercise_id,)).lastrowid
        db.execute("INSERT INTO runanswer (run_id,exercise_id,attempt_id) VALUES ('old-run',?,?)", (exercise_id,attempt_id))
        db.execute("INSERT INTO planweek VALUES ('2026-11-02',1,'2026-11-02 07:00:00')")
        db.execute("INSERT INTO studytask (id,plan_week,scheduled_date,original_date,subject,kind,title,instructions,planned_minutes,status,actual_minutes,completed_at,created_at) VALUES ('old-task','2026-11-02','2026-11-02','2026-11-02','english','practice','Keep this','My notes',20,'completed',23,'2026-11-02 07:30:00','2026-11-02 07:00:00')")
    before = snapshot(path)
    prepare(path, tmp_path / 'backups')
    assert_preserved(before, path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM vocabularycard').fetchone()[0] == 20
        assert db.execute('SELECT count(*) FROM vocabularyprogress').fetchone()[0] == 0
