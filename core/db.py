import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

REMINDER_COLUMNS = ("offer_reminded", "expiry_reminded")


def _migrate(db):
    """Add reminder columns to databases created before they existed."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
    for name in REMINDER_COLUMNS:
        if name not in columns:
            db.execute(f"ALTER TABLE sessions ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")


def connect(path: str = "queue.db") -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA.read_text())
    _migrate(db)
    db.commit()
    return db
