"""Salin database antrian ke folder backup tanpa menghentikan bot.

    docker exec turn-queue-bot python -m scripts.backup
    python -m scripts.backup            # kalau jalan langsung (bukan Docker)

Nama file: backup/queue-YYYY-MM-DD.db. File lama dipangkas sesuai BACKUP_KEEP_DAYS.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    db_path = Path(os.getenv("DB_PATH", "queue.db"))
    backup_dir = Path(os.getenv("BACKUP_DIR", str(db_path.parent / "backup")))
    keep = int(os.getenv("BACKUP_KEEP_DAYS", "14"))

    if not db_path.exists():
        print(f"database tidak ditemukan: {db_path}")
        return 1

    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"queue-{datetime.now(timezone.utc):%Y-%m-%d}.db"

    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        with destination:
            source.backup(destination)
    finally:
        source.close()
        destination.close()

    removed = 0
    for old in sorted(backup_dir.glob("queue-*.db"))[:-keep]:
        old.unlink()
        removed += 1

    print(f"{target} ({target.stat().st_size} bytes), {removed} backup lama dihapus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
