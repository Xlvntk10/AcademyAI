"""Back up, rehearse migrations on a copy, verify legacy rows, then upgrade.

Run with the API stopped. Copies are never deleted automatically.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ("skill", "lesson", "exercise", "attempt")


def connect_readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def verify(path):
    with connect_readonly(path) as db:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError(f"Integrity check failed: {path}")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError(f"Foreign key check failed: {path}")


def snapshot(path):
    with connect_readonly(path) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: db.execute(f'SELECT * FROM "{t}" ORDER BY id').fetchall() for t in LEGACY if t in tables}


def assert_preserved(before, path):
    after = snapshot(path)
    for table, rows in before.items():
        actual = {row[0]: row for row in after.get(table, [])}
        if any(actual.get(row[0]) != row for row in rows):
            raise RuntimeError(f"Original records changed: {table}")


def backup(source, destination):
    if destination.exists():
        raise FileExistsError(destination)
    with connect_readonly(source) as src, sqlite3.connect(destination) as dest:
        src.backup(dest)
    verify(destination)


def migrate(path):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = "sqlite:///" + path.resolve().as_posix()
    command.upgrade(cfg, "head")
    verify(path)


def prepare(path, backup_dir):
    path = path.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    trial = backup_dir / f"migration-trial-{stamp}.db"
    before = {}
    if path.exists():
        verify(path)
        before = snapshot(path)
        saved = backup_dir / f"academy-before-migration-{stamp}.db"
        backup(path, saved)
        backup(saved, trial)
        print(f"Verified backup: {saved}")
    migrate(trial)
    assert_preserved(before, trial)
    print(f"Migration rehearsal OK: {trial}")
    # Detect writes by another process between backup and migration.
    if path.exists() and snapshot(path) != before:
        raise RuntimeError("Database changed during rehearsal. Stop the API and retry.")
    migrate(path)
    assert_preserved(before, path)
    print("Migration OK. All original records preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "database.db")
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "backups")
    args = parser.parse_args()
    prepare(args.database, args.backup_dir)
