"""Logika antrian giliran. Tanpa Discord: semua state ada di SQLite.

Pakai `with db:` di pemanggil supaya satu kejadian = satu transaksi.
Waktu di DB disimpan sebagai ISO UTC; `now` bisa diinjeksi untuk tes.
"""
import math
from datetime import datetime, timedelta, timezone

BASE_DAYS = 7
OFFER_TIMEOUT = timedelta(hours=24)
OFFER_REMIND_AFTER = timedelta(hours=12)
EXPIRY_REMIND_WITHIN = timedelta(days=1)


class NotAllowed(Exception):
    """Aksi tidak valid (bukan gilirannya, double klik, dsb)."""


def _now(now):
    return now or datetime.now(timezone.utc)


def _iso(d):
    return d.isoformat(timespec="seconds")


# ---------- helper internal ----------

def _to_back(db, member_id):
    top = db.execute("SELECT COALESCE(MAX(queue_pos), 0) FROM members").fetchone()[0]
    db.execute(
        "UPDATE members SET status='queued', queue_pos=? WHERE discord_id=?",
        (top + 1, member_id),
    )


def _offer_next(db, now):
    row = db.execute(
        "SELECT discord_id FROM members WHERE status='queued' ORDER BY queue_pos LIMIT 1"
    ).fetchone()
    if not row:
        return None
    db.execute(
        "INSERT INTO sessions(member_id, status, offered_at) VALUES(?, 'offered', ?)",
        (row["discord_id"], _iso(now)),
    )
    return row["discord_id"]


def _close_offer(db, member_id):
    return db.execute(
        "UPDATE sessions SET status='ended' WHERE member_id=? AND status='offered'",
        (member_id,),
    ).rowcount


# ---------- aksi ----------

def seed_members(db, members):
    """members: [(discord_id, name), ...] sesuai urutan antrian awal. Hanya jalan sekali."""
    if db.execute("SELECT COUNT(*) FROM members").fetchone()[0]:
        return
    for pos, (discord_id, name) in enumerate(members, start=1):
        db.execute(
            "INSERT INTO members(discord_id, name, queue_pos, status) VALUES(?, ?, ?, 'queued')",
            (discord_id, name, pos),
        )


def start(db, now=None):
    """/admin start: tawarkan ke orang paling depan. None kalau sudah berjalan."""
    now = _now(now)
    busy = db.execute("SELECT 1 FROM sessions WHERE status IN ('offered','active')").fetchone()
    return None if busy else _offer_next(db, now)


def reset(db, members):
    """Paksa kembali ke awal: semua sesi ditutup, saldo 0, urutan = urutan members.

    Dipakai /admin reset. Anggota yang tidak ada di `members` ditaruh di belakang.
    """
    db.execute("UPDATE sessions SET status='ended' WHERE status IN ('offered','active')")
    db.execute("UPDATE members SET balance=0, status='queued', queue_pos=NULL")
    for pos, (discord_id, _name) in enumerate(members, start=1):
        db.execute("UPDATE members SET queue_pos=? WHERE discord_id=?", (pos, discord_id))
    rest = [
        r["discord_id"]
        for r in db.execute("SELECT discord_id FROM members WHERE queue_pos IS NULL ORDER BY name")
    ]
    for pos, discord_id in enumerate(rest, start=len(members) + 1):
        db.execute("UPDATE members SET queue_pos=? WHERE discord_id=?", (pos, discord_id))
    return len(members)


def accept(db, member_id, now=None):
    """Tombol Accept. Return jumlah hari sesi (7 + saldo)."""
    now = _now(now)
    if not _close_offer(db, member_id):
        raise NotAllowed("Tidak ada tawaran untukmu.")
    balance = db.execute(
        "SELECT balance FROM members WHERE discord_id=?", (member_id,)
    ).fetchone()["balance"]
    days = BASE_DAYS + balance
    db.execute(
        "INSERT INTO sessions(member_id, status, started_at, ends_at, days) VALUES(?, 'active', ?, ?, ?)",
        (member_id, _iso(now), _iso(now + timedelta(days=days)), days),
    )
    db.execute(
        "UPDATE members SET status='active', queue_pos=NULL, balance=0 WHERE discord_id=?",
        (member_id,),
    )
    return days


def skip(db, member_id, now=None):
    """Tombol Skip: +7, pindah belakang, status tetap inactive. Return orang yang ditawari berikutnya."""
    now = _now(now)
    if not _close_offer(db, member_id):
        raise NotAllowed("Tidak ada tawaran untukmu.")
    db.execute("UPDATE members SET balance = balance + ? WHERE discord_id=?", (BASE_DAYS, member_id))
    _to_back(db, member_id)
    return _offer_next(db, now)


def checkout(db, member_id, now=None):
    """/checkout atau waktu habis. Sisa hari (dibulatkan ke bawah) jadi saldo."""
    now = _now(now)
    row = db.execute(
        "SELECT id, ends_at FROM sessions WHERE member_id=? AND status='active'", (member_id,)
    ).fetchone()
    if not row:
        raise NotAllowed("Kamu sedang tidak memegang akses.")
    left = max(0, math.floor((datetime.fromisoformat(row["ends_at"]) - now).total_seconds() / 86400))
    db.execute("UPDATE sessions SET status='ended' WHERE id=?", (row["id"],))
    db.execute("UPDATE members SET balance = balance + ? WHERE discord_id=?", (left, member_id))
    _to_back(db, member_id)
    return _offer_next(db, now)


def _timeout(db, member_id, now):
    """Tidak merespons tawaran: pindah belakang, tanpa +7."""
    _close_offer(db, member_id)
    _to_back(db, member_id)
    return _offer_next(db, now)


def tick(db, now=None):
    """Dipanggil tiap menit. Return daftar member yang baru ditawari (untuk dinotifikasi)."""
    now = _now(now)
    newly = []
    for r in db.execute(
        "SELECT member_id FROM sessions WHERE status='active' AND ends_at<=?", (_iso(now),)
    ).fetchall():
        newly.append(checkout(db, r["member_id"], now))
    cutoff = _iso(now - OFFER_TIMEOUT)
    for r in db.execute(
        "SELECT member_id FROM sessions WHERE status='offered' AND offered_at<=?", (cutoff,)
    ).fetchall():
        newly.append(_timeout(db, r["member_id"], now))
    return [m for m in newly if m]


def due_reminders(db, now=None):
    """Return [(kind, member_id), ...] untuk pengingat yang belum pernah dikirim.

    Flag ditandai di pemanggilan yang sama, jadi tiap pengingat cuma sekali.
    """
    now = _now(now)
    out = []

    cutoff = _iso(now - OFFER_REMIND_AFTER)
    for r in db.execute(
        "SELECT member_id FROM sessions "
        "WHERE status='offered' AND offer_reminded=0 AND offered_at<=?",
        (cutoff,),
    ).fetchall():
        db.execute(
            "UPDATE sessions SET offer_reminded=1 WHERE member_id=? AND status='offered'",
            (r["member_id"],),
        )
        out.append(("offer_halfway", r["member_id"]))

    soon = _iso(now + EXPIRY_REMIND_WITHIN)
    for r in db.execute(
        "SELECT member_id FROM sessions "
        "WHERE status='active' AND expiry_reminded=0 AND ends_at>? AND ends_at<=?",
        (_iso(now), soon),
    ).fetchall():
        db.execute(
            "UPDATE sessions SET expiry_reminded=1 WHERE member_id=? AND status='active'",
            (r["member_id"],),
        )
        out.append(("expiry_soon", r["member_id"]))

    return out


# ---------- tampilan ----------

def status(db, now=None):
    """Data untuk /status: pemegang, tawaran berjalan, antrian + estimasi mulai, saldo semua."""
    now = _now(now)
    holder = db.execute(
        "SELECT m.discord_id, m.name, s.ends_at FROM sessions s "
        "JOIN members m ON m.discord_id = s.member_id WHERE s.status='active'"
    ).fetchone()
    offered = db.execute(
        "SELECT m.discord_id, m.name FROM sessions s "
        "JOIN members m ON m.discord_id = s.member_id WHERE s.status='offered'"
    ).fetchone()
    t = datetime.fromisoformat(holder["ends_at"]) if holder else now
    queue = []
    for r in db.execute(
        "SELECT discord_id, name, balance FROM members WHERE status='queued' ORDER BY queue_pos"
    ):
        queue.append({"discord_id": r["discord_id"], "name": r["name"], "balance": r["balance"], "eta": t})
        t += timedelta(days=BASE_DAYS + r["balance"])
    balances = {
        r["name"]: r["balance"]
        for r in db.execute(
            "SELECT name, balance FROM members "
            "ORDER BY queue_pos IS NULL DESC, queue_pos, name"
        )
    }
    return {"holder": holder, "offered": offered, "queue": queue, "balances": balances}
