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
        assert db.execute("SELECT count(*) FROM lessoncontent").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM exercisecontent").fetchone()[0] == 6
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
