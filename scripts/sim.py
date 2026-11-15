"""Dev-only walkthrough of the queue rules without Discord or a bot token.

Runs against a throwaway SQLite file and prints the state after each event.
Not part of the bot. Run from the repo root: `python -m scripts.sim`.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.timefmt import fmt_wib
from core import turns
from core.db import connect

MEMBERS = [("1", "dzikra"), ("2", "locke"), ("3", "radrtma"), ("4", "kjaer")]


def show(db, now):
    snap = turns.status(db, now)
    holder, offered = snap["holder"], snap["offered"]
    print("   main    :", f"{holder['name']} sampai {fmt_wib(holder['ends_at'])}" if holder else "-")
    print("   tawaran :", offered["name"] if offered else "-")
    queue = ", ".join(f"{i['name']}(saldo {i['balance']}, mulai {fmt_wib(i['eta'])})" for i in snap["queue"])
    print("   antrian :", queue or "-")
    print("   saldo   :", ", ".join(f"{n} {d}" for n, d in snap["balances"].items()))


def step(label):
    print(f"\n== {label}")


def main():
    tmp = Path(tempfile.mkdtemp()) / "sim.db"
    db = connect(tmp)
    with db:
        turns.seed_members(db, MEMBERS)

    t0 = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)

    step("awal (IDLE)")
    show(db, t0)

    step("admin start -> tawaran ke dzikra")
    with db:
        print("   ditawari:", turns.start(db, t0))
    show(db, t0)

    step("orang lain (locke) klik Accept -> NotAllowed, state tidak berubah")
    try:
        with db:
            turns.accept(db, "2", t0)
    except turns.NotAllowed as exc:
        print("   ditolak :", exc.lines[0] if hasattr(exc, "lines") else exc)
    show(db, t0)

    step("dzikra Accept -> 7 hari")
    with db:
        days = turns.accept(db, "1", t0)
    print("   hari    :", days)
    show(db, t0)

    step("2 hari kemudian dzikra /checkout -> sisa 5 hari jadi saldo")
    t1 = t0 + timedelta(days=2)
    with db:
        nxt = turns.checkout(db, "1", t1)
    print("   ditawari:", nxt)
    show(db, t1)

    step("locke Skip -> saldo +7, ke belakang, radrtma ditawari")
    with db:
        nxt = turns.skip(db, "2", t1)
    print("   ditawari:", nxt)
    show(db, t1)

    step("25 jam kemudian radrtma tidak jawab -> timeout, kjaer ditawari")
    t2 = t1 + timedelta(hours=25)
    with db:
        newly = turns.tick(db, t2)
    print("   ditawari:", newly)
    show(db, t2)

    step("kjaer Accept -> 7 hari, antrian tinggal dzikra/locke/radrtma")
    with db:
        days = turns.accept(db, "4", t2)
    print("   hari    :", days)
    show(db, t2)

    print(f"\ndb sementara: {tmp} (aman dihapus)")
    db.close()


if __name__ == "__main__":
    main()
