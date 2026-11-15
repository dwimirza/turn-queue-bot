"""Environment configuration. Fails fast when a required variable is missing."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

REQUIRED = ("DISCORD_TOKEN", "GUILD_ID", "NOTIFY_CHANNEL_ID", "MEMBERS")


@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int
    notify_channel_id: int
    admin_role_id: int | None
    members: list[tuple[str, str]]
    db_path: str


def parse_members(raw: str) -> list[tuple[str, str]]:
    """Parse `id:name,id:name` into queue order. Raises ValueError on a bad value."""
    members: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"MEMBERS entry {part!r} is missing ':'")
        discord_id, name = part.split(":", 1)
        discord_id, name = discord_id.strip(), name.strip()
        if not discord_id or not name:
            raise ValueError(f"MEMBERS entry {part!r} needs both an id and a name")
        members.append((discord_id, name))
    if not members:
        raise ValueError("MEMBERS is empty")
    return members


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env: {name}")
    return value


def _int_env(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from None


def load_settings() -> Settings:
    load_dotenv()
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Missing required env: " + ", ".join(missing))

    try:
        members = parse_members(os.environ["MEMBERS"])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    admin_raw = os.getenv("ADMIN_ROLE_ID", "").strip()
    return Settings(
        token=_required("DISCORD_TOKEN"),
        guild_id=_int_env("GUILD_ID", os.environ["GUILD_ID"].strip()),
        notify_channel_id=_int_env("NOTIFY_CHANNEL_ID", os.environ["NOTIFY_CHANNEL_ID"].strip()),
        admin_role_id=_int_env("ADMIN_ROLE_ID", admin_raw) if admin_raw else None,
        members=members,
        db_path=os.getenv("DB_PATH", "queue.db").strip() or "queue.db",
    )
