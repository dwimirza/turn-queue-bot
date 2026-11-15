from datetime import datetime, timedelta, timezone

import pytest

from core import turns as q
from core.db import connect

T0 = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)


def day(n, hours=0):
    return T0 + timedelta(days=n, hours=hours)


@pytest.fixture
def db():
    d = connect(":memory:")
    q.seed_members(d, [("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")])
    return d


def balances(db):
    return {r["name"]: r["balance"] for r in db.execute("SELECT name, balance FROM members")}


def order(db):
    return [r["name"] for r in db.execute("SELECT name FROM members WHERE status='queued' ORDER BY queue_pos")]


def test_scenario_abcd(db):
    assert q.start(db, T0) == "A"
    assert q.accept(db, "A", T0) == 7

    # hari ke-3 A checkout, sisa 4 hari jadi saldo, tawaran ke B
    assert q.checkout(db, "A", day(3)) == "B"
    assert balances(db)["A"] == 4
    assert order(db) == ["B", "C", "D", "A"]

    # B skip: +7, ke belakang, tawaran ke C
    assert q.skip(db, "B", day(3)) == "C"
    assert balances(db)["B"] == 7
    assert order(db) == ["C", "D", "A", "B"]

    # C accept, 7 hari
    assert q.accept(db, "C", day(3)) == 7
    assert order(db) == ["D", "A", "B"]

    # C habis otomatis, tawaran ke D
    assert q.tick(db, day(10)) == ["D"]
    assert order(db) == ["D", "A", "B", "C"]

    # D main penuh 7 hari, tawaran ke A
    assert q.accept(db, "D", day(10)) == 7
    assert q.tick(db, day(17)) == ["A"]
    assert order(db) == ["A", "B", "C", "D"]

    # A accept: 7 + 4 = 11 hari, saldo A jadi 0
    assert q.accept(db, "A", day(17)) == 11
    assert balances(db)["A"] == 0

    # A habis, B accept: 7 + 7 = 14 hari
    assert q.tick(db, day(28)) == ["B"]
    assert q.accept(db, "B", day(28)) == 14
    assert balances(db) == {"A": 0, "B": 0, "C": 0, "D": 0}
    assert order(db) == ["C", "D", "A"]


def test_checkout_rounds_down(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    q.checkout(db, "A", day(3, hours=5))  # sisa 3.79 hari
    assert balances(db)["A"] == 3


def test_only_offered_member_can_accept_or_skip(db):
    q.start(db, T0)  # tawaran untuk A
    with pytest.raises(q.NotAllowed):
        q.accept(db, "B", T0)
    with pytest.raises(q.NotAllowed):
        q.skip(db, "B", T0)


def test_double_click_does_not_double_count(db):
    q.start(db, T0)
    q.skip(db, "A", T0)
    with pytest.raises(q.NotAllowed):
        q.skip(db, "A", T0)
    assert balances(db)["A"] == 7


def test_checkout_without_active_session(db):
    with pytest.raises(q.NotAllowed):
        q.checkout(db, "A", T0)


def test_offer_timeout_moves_back_without_bonus(db):
    q.start(db, T0)
    assert q.tick(db, T0 + timedelta(hours=23)) == []
    assert q.tick(db, T0 + timedelta(hours=25)) == ["B"]
    assert balances(db)["A"] == 0
    assert order(db) == ["B", "C", "D", "A"]


def test_start_twice_does_nothing(db):
    assert q.start(db, T0) == "A"
    assert q.start(db, T0) is None


def test_tick_is_idempotent(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    assert q.tick(db, day(7)) == ["B"]
    assert q.tick(db, day(7)) == []


def test_status_eta(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    s = q.status(db, T0)
    assert s["holder"]["name"] == "A"
    assert [x["name"] for x in s["queue"]] == ["B", "C", "D"]
    assert s["queue"][0]["eta"] == day(7)
    assert s["queue"][1]["eta"] == day(14)


def test_offer_reminder_fires_once_after_12_hours(db):
    q.start(db, T0)
    assert q.due_reminders(db, T0 + timedelta(hours=11)) == []
    assert q.due_reminders(db, T0 + timedelta(hours=12)) == [("offer_halfway", "A")]
    assert q.due_reminders(db, T0 + timedelta(hours=13)) == []


def test_offer_reminder_not_sent_for_expired_offer(db):
    q.start(db, T0)
    q.tick(db, T0 + timedelta(hours=25))  # A timeout, B ditawari
    assert q.due_reminders(db, T0 + timedelta(hours=26)) == []
    assert q.due_reminders(db, T0 + timedelta(hours=37)) == [("offer_halfway", "B")]


def test_expiry_reminder_fires_once_within_one_day(db):
    q.start(db, T0)
    q.accept(db, "A", T0)  # habis di day(7)
    assert q.due_reminders(db, day(5, hours=23)) == []
    assert q.due_reminders(db, day(6)) == [("expiry_soon", "A")]
    assert q.due_reminders(db, day(6, hours=2)) == []


def test_expiry_reminder_skipped_when_time_already_up(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    assert q.due_reminders(db, day(7)) == []
    assert q.due_reminders(db, day(8)) == []


def test_expiry_reminder_resets_for_next_session(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    assert q.due_reminders(db, day(6)) == [("expiry_soon", "A")]
    q.tick(db, day(7))  # sesi A habis, tawaran ke B
    q.accept(db, "B", day(7))
    assert q.due_reminders(db, day(12)) == []
    assert q.due_reminders(db, day(13)) == [("expiry_soon", "B")]


def test_reset_restores_initial_state(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    q.checkout(db, "A", day(3))  # saldo A = 4
    q.skip(db, "B", day(3))      # saldo B = 7
    q.reset(db, [("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")])

    assert order(db) == ["A", "B", "C", "D"]
    assert balances(db) == {"A": 0, "B": 0, "C": 0, "D": 0}
    snap = q.status(db, day(3))
    assert snap["holder"] is None and snap["offered"] is None
    assert q.start(db, day(3)) == "A"


def test_reset_closes_running_session(db):
    q.start(db, T0)
    q.accept(db, "A", T0)
    q.reset(db, [("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")])

    active = db.execute("SELECT COUNT(*) FROM sessions WHERE status='active'").fetchone()[0]
    offered = db.execute("SELECT COUNT(*) FROM sessions WHERE status='offered'").fetchone()[0]
    assert (active, offered) == (0, 0)
    # tidak ada sisa sesi yang "hidup" lagi, jadi tick tidak menawarkan siapa pun
    assert q.tick(db, day(30)) == []
