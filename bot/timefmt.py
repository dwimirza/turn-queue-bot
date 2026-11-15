"""Display helpers. Stored times stay UTC; this only formats them."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
DAYS = ("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def fmt_wib(value: datetime | str) -> str:
    """Format a UTC time as `Sen 16 Nov, 16:00 WIB`."""
    local = as_utc(value).astimezone(WIB)
    return f"{DAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, {local:%H:%M} WIB"


def remaining(ends: datetime | str, now: datetime) -> str:
    seconds = int((as_utc(ends) - as_utc(now)).total_seconds())
    if seconds < 0:
        seconds = 0
    days, rem = divmod(seconds, 86400)
    hours = rem // 3600
    return f"{days} hari {hours} jam"
