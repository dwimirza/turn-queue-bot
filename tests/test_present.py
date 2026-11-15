from datetime import datetime, timezone

from bot.present import status_embed

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)


def fields(embed):
    return {field.name: field.value for field in embed.fields}


def test_offered_person_not_duplicated_and_shows_allotment():
    snap = {
        "holder": None,
        "offered": {"discord_id": "1", "name": "A"},
        "queue": [
            {"discord_id": "1", "name": "A", "balance": 0, "eta": NOW},
            {"discord_id": "2", "name": "B", "balance": 3, "eta": NOW},
        ],
        "balances": {"A": 0, "B": 3},
    }
    embed_fields = fields(status_embed(snap, NOW))

    assert "jatah 7 hari" in embed_fields["Tawaran"].lower() or "7 hari" in embed_fields["Tawaran"]
    assert "A" not in embed_fields["Antrian"]  # offered person listed once only
    assert "B — 10 hari (3 cadangan)" in embed_fields["Antrian"]


def test_idle_status_shows_base_allotment_for_everyone():
    snap = {
        "holder": None,
        "offered": None,
        "queue": [
            {"discord_id": "1", "name": "A", "balance": 0, "eta": NOW},
            {"discord_id": "2", "name": "B", "balance": 7, "eta": NOW},
        ],
        "balances": {"A": 0, "B": 7},
    }
    embed_fields = fields(status_embed(snap, NOW))

    assert "Antrian belum jalan" in status_embed(snap, NOW).description
    assert "A — 7 hari — mulai" in embed_fields["Antrian"]
    assert "B — 14 hari (7 cadangan)" in embed_fields["Antrian"]
    assert "Jatah tiap giliran = 7 + cadangan" in embed_fields["Cadangan"]
