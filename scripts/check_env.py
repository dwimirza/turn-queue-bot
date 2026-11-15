"""Dev-only preflight check: verifies .env values against the Discord API.

Uses only the standard library (urllib). Run from the repo root:
    python -m scripts.check_env

Checks that the token works, NOTIFY_CHANNEL_ID is a text channel in GUILD_ID,
every MEMBERS id is a member of that guild, and ADMIN_ROLE_ID exists.
Never prints the token.
"""

import json
import sys
import urllib.error
import urllib.request

from bot.config import load_settings

API = "https://discord.com/api/v10"
TEXT_CHANNEL_TYPES = {0, 5}  # text, announcement
CHANNEL_KINDS = {
    0: "text",
    2: "voice",
    4: "category",
    5: "announcement",
    10: "announcement thread",
    11: "public thread",
    12: "private thread",
    13: "stage",
    15: "forum",
    16: "media",
}


def call(path: str, token: str):
    request = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "queue-bot-env-check (1.0)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return None, f"HTTP {exc.code} {body[:180]}"
    except urllib.error.URLError as exc:
        return None, f"network error: {exc.reason}"


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    return ok


def list_text_channels(channels) -> None:
    if not channels:
        return
    print("       text channels the bot can see here:")
    for channel in channels:
        if channel["type"] in TEXT_CHANNEL_TYPES:
            print(f"         #{channel['name']:<24} {channel['id']}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = load_settings()
    failures = 0

    me, err = call("/users/@me", settings.token)
    if not check("DISCORD_TOKEN valid", me is not None, me["username"] if me else err):
        print("\nToken rejected. Reset it in the Developer Portal and update .env.")
        return 1

    guild, err = call(f"/guilds/{settings.guild_id}", settings.token)
    failures += not check(
        "GUILD_ID reachable",
        guild is not None,
        guild["name"] if guild else f"{err} (is the bot invited to this server?)",
    )

    channels, channels_err = call(f"/guilds/{settings.guild_id}/channels", settings.token)
    channel, channel_err = call(f"/channels/{settings.notify_channel_id}", settings.token)

    if channel is None:
        failures += not check(
            "NOTIFY_CHANNEL_ID exists",
            False,
            channel_err or "unknown channel (deleted, or copied from a DM)",
        )
        list_text_channels(channels)
    elif str(channel.get("guild_id")) != str(settings.guild_id):
        other, _ = call(f"/guilds/{channel['guild_id']}", settings.token) if channel.get("guild_id") else (None, None)
        failures += not check(
            "NOTIFY_CHANNEL_ID is in this guild",
            False,
            f"#{channel['name']} belongs to {other['name'] if other else channel.get('guild_id')}",
        )
    elif channel["type"] not in TEXT_CHANNEL_TYPES:
        kind = CHANNEL_KINDS.get(channel["type"], f"type {channel['type']}")
        failures += not check(
            "NOTIFY_CHANNEL_ID is a text channel",
            False,
            f"#{channel['name']} is a {kind} channel; pick a normal text channel",
        )
    else:
        failures += not check(
            "NOTIFY_CHANNEL_ID is a text channel",
            True,
            f"#{channel['name']} in {guild['name'] if guild else settings.guild_id}",
        )

    if channels_err:
        check("guild channel list", True, f"not readable ({channels_err}), checked the channel directly")

    roles, roles_err = call(f"/guilds/{settings.guild_id}/roles", settings.token)
    if settings.admin_role_id is not None:
        role = None
        if roles:
            role = next((r for r in roles if r["id"] == str(settings.admin_role_id)), None)
        failures += not check(
            "ADMIN_ROLE_ID exists",
            role is not None,
            role["name"] if role else (roles_err or "role not in this guild"),
        )
    else:
        check("ADMIN_ROLE_ID unset", True, "falls back to Manage Server")

    print("\nMEMBERS (queue order):")
    for pos, (discord_id, name) in enumerate(settings.members, start=1):
        member, member_err = call(f"/guilds/{settings.guild_id}/members/{discord_id}", settings.token)
        if member is None:
            failures += 1
        user = (member or {}).get("user", {})
        label = user.get("global_name") or user.get("username") or "?"
        print(
            f"  {pos}. {name:<10} {discord_id:<20} "
            + (f"-> @{label}" if member else f"-> FAIL ({member_err})")
        )

    print("\nAlso make sure the bot role can View Channel + Send Messages + Embed Links")
    print("in the notify channel, otherwise offers will fail to send (logged, not fatal).")
    print("\nFAILED: fix the items above." if failures else "\nAll good. You can run: python -m bot.main")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
