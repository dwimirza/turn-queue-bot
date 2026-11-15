# Turn Queue Discord Bot: Spec

Source of truth for requirements and scope. Read fully before writing code.

## 1. Goal

A Discord bot that shares **one game access (GTA 6)** among a fixed group of 4 people by turns.

- Turns are a **queue**, not a calendar.
- A session lasts **7 days**, plus any saved **balance** (days).
- Skipping a turn or finishing early adds to the person's balance. The balance is applied automatically to their next session.
- "Balance" is just a count of days. It is not money.

Group members (fixed, no join/leave): **dzikra, locke, radrtma, kjaer**. Initial queue order = that order (confirm with owner; it is configured via env, see section 6).

## 2. Current status

| Step | Status |
|---|---|
| 1. Core logic + SQLite schema + tests (`core/`, `schema.sql`, `tests/`) | **DONE**, 9 tests pass. Do not rewrite. Extend only where this spec says so. |
| 2. Discord layer (`bot/`) | **DONE** — code complete; manual checklist in §12 still to run in a test server. |
| 3. Reminders | **DONE** — `offer_halfway` (12h) + `expiry_soon` (<=1 day), flags migrated in `core/db.py`. |
| 4. Deploy | TODO |

## 3. Domain rules (already implemented in `core/turns.py`)

State of the system is always one of:

- **IDLE**: nobody holds access, no pending offer.
- **OFFERED**: the person at the front of the queue has been offered the turn (buttons Accept / Skip). Access is inactive, so **no days are consumed**.
- **ACTIVE**: one person holds access until `ends_at`. Days are consumed by calendar time (`ends_at - now`); there is no daily job.

Transitions:

| Event | Effect |
|---|---|
| `/admin start` (only when IDLE) | Offer to the front of the queue. |
| **Accept** (by the offered person only) | `days = 7 + balance`, balance becomes 0, `ends_at = now + days`, person leaves the queue, status ACTIVE. |
| **Skip** (by the offered person only) | balance `+7`, person goes to the back of the queue, state stays inactive, offer goes to the new front. Nothing is deducted. |
| `/checkout` (by the holder only) | Remaining time, **rounded down to whole days**, is added to balance. Holder goes to the back of the queue. Offer goes to the new front. |
| Session time runs out (`ends_at <= now`) | Same as checkout with 0 days left. Done by the periodic `tick()`. |
| Offer not answered for **24 hours** | Person goes to the back of the queue, **no +7**, offer goes to the new front. Done by `tick()`. |

Rules and decisions (do not change):

- Balance rollover is unlimited. No cap on session length.
- Only one ACTIVE and one OFFERED session can exist at once (enforced by unique indexes in `schema.sql`).
- Buttons only for Accept/Skip. There is **no** `/checkin`, `/join`, `/leave`, or `/skip` command.
- All state lives in SQLite. No in-memory timers. The bot must behave correctly after a restart.
- Times are stored as ISO-8601 UTC strings. Display in **WIB** (`Asia/Jakarta`).

## 4. Data model (`schema.sql`, already exists)

```
members(discord_id TEXT PK, name TEXT, balance INT, queue_pos INT NULL, status 'queued'|'active')
sessions(id PK, member_id FK, status 'offered'|'active'|'ended',
         offered_at, started_at, ends_at, days)
```

Only two tables. No ledger/history table and no config table (explicitly dropped).

## 5. Existing core API (`core/turns.py`, `core/db.py`)

All functions take an open `sqlite3.Connection` (`row_factory = sqlite3.Row`) and an optional `now` (UTC datetime, for tests). Callers wrap each event in `with db:` so one event = one transaction.

```
db.connect(path) -> Connection                  # applies schema.sql
turns.seed_members(db, [(discord_id, name), ...])   # in queue order; no-op if members exist
turns.start(db) -> member_id | None             # None if already OFFERED/ACTIVE
turns.accept(db, member_id) -> int days         # raises NotAllowed
turns.skip(db, member_id) -> next_member_id | None   # raises NotAllowed
turns.checkout(db, member_id) -> next_member_id | None  # raises NotAllowed
turns.tick(db) -> [member_id, ...]              # newly offered people, to notify
turns.status(db) -> {
    "holder":  Row(discord_id, name, ends_at) | None,   # ends_at is an ISO UTC string
    "offered": Row(discord_id, name) | None,
    "queue":   [{discord_id, name, balance, eta: datetime}, ...],  # in order; eta = estimated start
    "balances": {name: balance}
}
turns.NotAllowed                                # exception: invalid action (wrong person, double click)
```

Return value `None` from `skip`/`checkout`/`tick` means nobody to offer to. This should not happen with 4 members.

## 6. Configuration (`.env`, never committed)

```
DISCORD_TOKEN=...            # bot token (secret)
GUILD_ID=...                 # the one server
NOTIFY_CHANNEL_ID=...        # channel for offer/handover messages
ADMIN_ROLE_ID=...            # role allowed to use /admin start (optional; if unset, require Manage Server)
MEMBERS=id1:dzikra,id2:locke,id3:radrtma,id4:kjaer   # Discord user ID : name, in initial queue order
DB_PATH=queue.db             # optional
```

Load with `python-dotenv`. Fail fast with a clear message if a required variable is missing.

## 7. Step 2: Discord layer (`bot/`)

Entry point: `python -m bot.main`. Library: `discord.py` 2.x, default intents only (no message content, no privileged intents). All commands are slash commands registered **to the single guild** (fast sync).

Suggested order of work: 2a skeleton + `/status`, 2b offer message + buttons, 2c `/checkout` + `/admin start`, 2d tick loop.

### 7.1 Startup (`setup_hook`)

1. `db = connect(DB_PATH)`.
2. `seed_members(db, MEMBERS)` (does nothing if already seeded).
3. Register the persistent offer view: `bot.add_view(OfferView())` so buttons keep working after a restart.
4. Sync slash commands to the guild.
5. Start the tick loop (7.6).

Use one shared connection. The bot runs in one asyncio loop, and the SQLite calls are short and synchronous. That is fine here.

### 7.2 Offer message: `notify(member_id)`

Posts to `NOTIFY_CHANNEL_ID`:

- Content: mention of the member (`<@id>`) so they get pinged.
- Embed: title "Giliran kamu", text showing the session length if accepted (`7 + balance` days) and what Skip does (back of queue, balance +7).
- View: two buttons, **Accept** (success style) and **Skip** (secondary).

Send the message **after** the DB transaction has committed. If sending fails, log the error. Do not crash.

### 7.3 Buttons (`OfferView`)

- `timeout=None`; fixed `custom_id`s `offer:accept` and `offer:skip` (required for persistence).
- Identify the person by `interaction.user.id`. Do not store the target in the view. The core already rejects anyone who has no pending offer by raising `NotAllowed`.
- **Accept:** `with db: days = turns.accept(db, uid)`. On success, edit the original message: remove the buttons and write that `<@uid>` plays for `days` days until `<ends_at in WIB>`.
- **Skip:** `with db: nxt = turns.skip(db, uid)`. On success, edit the original message: remove the buttons and write that `<@uid>` skipped (balance +7). Then `notify(nxt)` if `nxt`.
- On `NotAllowed`: reply **ephemeral** ("Bukan tawaran untukmu, atau sudah diproses."). Never change state.
- Double clicks and races are already harmless because the core checks the offer status inside the transaction.

### 7.4 Commands

| Command | Who | Behavior |
|---|---|---|
| `/status` | anyone | Public embed: current holder + time left (days/hours) and end time in WIB; pending offer (who); queue in order with estimated start (WIB date) and balance each; balances of everyone. Handle IDLE (nobody holds, no offer) gracefully. |
| `/checkout` | holder only | `with db: nxt = turns.checkout(db, uid)`. Reply publicly with how many days were saved to balance (read balance before and after). Then `notify(nxt)`. `NotAllowed` → ephemeral error. |
| `/admin start` | members of `ADMIN_ROLE_ID` (or Manage Server if unset) | `with db: first = turns.start(db)`. If `None`, reply "sudah berjalan". Else `notify(first)`. |
| `/admin reset` | same as `/admin start` | Ephemeral confirm button, then `with db: turns.reset(db, MEMBERS)`: close every `offered`/`active` session, put everyone back in `MEMBERS` order, balances to 0. No message is sent afterwards. |

Anyone who is not in `members` and uses a command gets an ephemeral "Kamu bukan anggota antrian".

### 7.5 Time display

Helper `fmt_wib(dt)` that converts a UTC datetime to `Asia/Jakarta` via `zoneinfo` and formats like `Sen 16 Nov, 16:00 WIB` (Indonesian day names). Add the `tzdata` package to `requirements.txt` for Windows. DB values stay UTC.

### 7.6 Tick loop

`discord.ext.tasks.loop(seconds=60)`:

```
await bot.wait_until_ready()
with db: newly = turns.tick(db)
for member_id in newly: await notify(member_id)
```

Wrap the body in `try/except Exception` and log, because an unhandled exception stops a `tasks.loop`. On the first tick after a restart, anything that expired while the bot was down is processed automatically.

### 7.7 Language and tone

All user-facing text is **Indonesian**, short and casual. Code, identifiers, and comments are English.

## 8. Step 3: Reminders (optional)

Implemented: flags live in `schema.sql` and are added to older databases by `core/db.py`;
`turns.due_reminders(db, now)` is called from the tick loop in `bot/main.py`.

Add two flags to `sessions`: `offer_reminded`, `expiry_reminded` (INTEGER DEFAULT 0). Since `CREATE TABLE IF NOT EXISTS` won't alter an existing DB, add a small `ALTER TABLE` migration on connect (or tell the owner to delete `queue.db` in dev).

Add to `core/turns.py`: `due_reminders(db, now) -> [(kind, member_id), ...]`, which marks the flag in the same call so each reminder fires once.

- `offer_halfway`: offered and not answered after 12 hours.
- `expiry_soon`: active session with 1 day or less left.

`tick` loop sends the messages in the notify channel. Add unit tests for both kinds and for "fires only once".

## 9. Step 4: Deploy

- Run as a long-lived service: Docker (`python:3.12-slim`, `restart: unless-stopped`) or `systemd` with `Restart=always`.
- Keep `queue.db` on a persistent volume.
- Daily backup via cron: `sqlite3 queue.db ".backup 'backup/queue-$(date +%F).db'"`.
- Write a short `README.md`: setup, `.env`, run, test.

## 10. Out of scope (do NOT build)

Ledger/history table or `/history`; config table; `/join`, `/leave`, `/checkin`, a skip slash command; session length cap; multi-server support; web dashboard; payments; DM-based flows; handling "nobody ever plays" scenarios; any change to the rules in section 3.

## 11. Engineering rules

- Python 3.11+. Dependencies: `discord.py>=2.4`, `python-dotenv`, `tzdata`, `pytest`. Ask before adding anything else.
- `core/` never imports `discord`. All game rules stay in `core/turns.py`. The Discord layer only calls it and renders results.
- Keep it small and readable. No ORM, no async DB wrapper, no abstractions "for later".
- Any new core function gets tests in `tests/`. Run `python -m pytest` and keep it green before finishing any task.
- Do not change existing behavior in `core/turns.py` unless a test proves a bug. Update tests and this spec if a rule changes.
- Never commit secrets. `.env` and `*.db` are in `.gitignore`.

## 12. Acceptance checklist (manual, in a test server)

Time-based behavior (expiry, 24h timeout) is covered by unit tests. Manually verify:

1. `/status` before start shows IDLE and the queue order dzikra, locke, radrtma, kjaer.
2. `/admin start` as a non-admin is refused; as an admin it pings the first person with Accept/Skip.
3. Someone else clicking the buttons gets an ephemeral refusal, and nothing changes.
4. Accept: message updates, buttons disappear, `/status` shows the holder and end time in WIB, and the first person leaves the queue.
5. `/checkout` by the holder: saved days appear in balance, the next person is pinged.
6. Skip by the next person: balance is +7, they move to the back, the following person is pinged, and nothing was deducted.
7. Click Accept twice quickly: the second click gets the ephemeral refusal.
8. Restart the bot while an offer is pending: the old buttons still work.
9. `python -m pytest` passes.
10. `/admin reset` asks for confirmation, then `/status` is IDLE with the initial order and all balances 0.
