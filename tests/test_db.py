import sqlite3

from core.db import connect

OLD_SCHEMA = """
CREATE TABLE members (
  discord_id TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  balance    INTEGER NOT NULL DEFAULT 0,
  queue_pos  INTEGER,
  status     TEXT NOT NULL CHECK (status IN ('queued', 'active'))
);
CREATE TABLE sessions (
  id         INTEGER PRIMARY KEY,
  member_id  TEXT NOT NULL REFERENCES members(discord_id),
  status     TEXT NOT NULL CHECK (status IN ('offered', 'active', 'ended')),
  offered_at TEXT,
  started_at TEXT,
  ends_at    TEXT,
  days       INTEGER
);
"""

NEW_COLUMNS = ("offer_reminded", "expiry_reminded")


def test_connect_adds_reminder_columns_to_old_db(tmp_path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(OLD_SCHEMA)
    raw.commit()
    raw.close()

    db = connect(str(path))
    columns = {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}
    assert set(NEW_COLUMNS) <= columns


def test_old_rows_get_zero_default(tmp_path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(OLD_SCHEMA)
    raw.execute("INSERT INTO members(discord_id, name, status) VALUES('A', 'A', 'queued')")
    raw.execute(
        "INSERT INTO sessions(member_id, status, offered_at) "
        "VALUES('A', 'offered', '2026-01-01T00:00:00+00:00')"
    )
    raw.commit()
    raw.close()

    db = connect(str(path))
    row = db.execute("SELECT offer_reminded, expiry_reminded FROM sessions").fetchone()
    assert (row["offer_reminded"], row["expiry_reminded"]) == (0, 0)


def test_connect_creates_missing_parent_directory(tmp_path):
    # DB_PATH=data/queue.db must not fail with "unable to open database file".
    path = tmp_path / "data" / "queue.db"
    db = connect(str(path))
    assert path.exists()
    assert db.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0
    db.close()


def test_connect_keeps_schema_and_pragmas(tmp_path):
    db = connect(str(tmp_path / "queue.db"))
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    by_id = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='one_active'"
    ).fetchone()
    assert by_id is not None
    db.close()

