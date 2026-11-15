import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

REMINDER_COLUMNS = ("offer_reminded", "expiry_reminded")

# One process writes at a time; a short wait beats an immediate "database is locked".
BUSY_TIMEOUT_MS = 5000


def _migrate(db):
    """Add reminder columns to databases created before they existed."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
    for name in REMINDER_COLUMNS:
        if name not in columns:
            db.execute(f"ALTER TABLE sessions ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")


def _prepare_path(path: str) -> bool:
    """Create the parent directory if needed. Return True for a file-backed DB."""
    if path == ":memory:":
        return False
    parent = Path(path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    return True


def connect(path: str = "queue.db") -> sqlite3.Connection:
    on_disk = _prepare_path(path)
    db = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    if on_disk:
        # WAL keeps readers (backups) from blocking the bot and survives crashes better.
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA synchronous = NORMAL")
    # Always read the schema as UTF-8: the file has non-ASCII comments and the
    # platform default is cp1252 on Windows.
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrate(db)
    db.commit()
    return db
