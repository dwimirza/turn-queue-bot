# AGENTS.md

Read `SPEC.md` first. It is the source of truth for requirements, scope, and the order of work.

- Python 3.11+, discord.py 2.x, SQLite via the standard library. Ask before adding dependencies.
- `core/` must never import `discord`. All game rules live in `core/turns.py` and are covered by tests.
- Run `python -m pytest` before finishing any task. Keep all tests passing.
- User-facing bot text is Indonesian. Code, identifiers, and comments are English.
- Never commit secrets (`.env`, tokens).
- Do not build anything listed under "Out of scope" in `SPEC.md`.
- Current task: Step 2 (Discord layer in `bot/`). Step 1 is done.
