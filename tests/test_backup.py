"""`scripts/backup.py` must produce a readable copy and never prune too much."""

import sqlite3
from datetime import datetime, timezone

from core import turns
from core.db import connect
from scripts import backup


def make_db(path) -> None:
    db = connect(str(path))
    with db:
        turns.seed_members(db, [("1", "dzikra"), ("2", "locke")])
    db.close()


def old_backup(backup_dir, day: str):
    path = backup_dir / f"queue-{day}.db"
    path.write_bytes(b"")
    return path


def test_backup_writes_a_readable_copy(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "queue.db"
    make_db(db_path)
    backup_dir = tmp_path / "backup"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    assert backup.main() == 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = backup_dir / f"queue-{today}.db"
    assert target.exists()
    copy = sqlite3.connect(target)
    assert copy.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 2
    copy.close()


def test_backup_prunes_old_files_but_keeps_the_new_one(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "queue.db"
    make_db(db_path)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir(parents=True)
    for day in ("2020-01-01", "2020-01-02", "2020-01-03"):
        old_backup(backup_dir, day)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("BACKUP_KEEP_DAYS", "2")

    assert backup.main() == 0

    kept = sorted(p.name for p in backup_dir.glob("queue-*.db"))
    assert len(kept) == 2
    assert "queue-2020-01-01.db" not in kept and "queue-2020-01-02.db" not in kept


def test_backup_keep_zero_still_keeps_todays_file(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "queue.db"
    make_db(db_path)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir(parents=True)
    old_backup(backup_dir, "2020-01-01")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("BACKUP_KEEP_DAYS", "0")

    assert backup.main() == 0
    assert [p.name for p in backup_dir.glob("queue-*.db")] != []
