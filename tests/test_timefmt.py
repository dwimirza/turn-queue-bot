from datetime import datetime, timezone

from bot.timefmt import fmt_wib, remaining


def test_fmt_wib_matches_spec_example():
    # 09:00 UTC is 16:00 in Asia/Jakarta. 16 Nov 2026 is a Monday.
    dt = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
    assert fmt_wib(dt) == "Sen 16 Nov, 16:00 WIB"
    assert fmt_wib("2026-11-16T09:00:00+00:00") == "Sen 16 Nov, 16:00 WIB"


def test_fmt_wib_sunday():
    dt = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
    assert fmt_wib(dt) == "Min 15 Nov, 16:00 WIB"


def test_remaining_days_and_hours():
    now = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
    ends = datetime(2026, 11, 19, 12, 30, tzinfo=timezone.utc)
    assert remaining(ends, now) == "3 hari 3 jam"
