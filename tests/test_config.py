import pytest

from bot.config import parse_members


def test_parse_members_keeps_queue_order():
    raw = "1:dzikra, 2:locke,3:radrtma,4:kjaer"
    assert parse_members(raw) == [
        ("1", "dzikra"),
        ("2", "locke"),
        ("3", "radrtma"),
        ("4", "kjaer"),
    ]


def test_parse_members_rejects_bad_entry():
    with pytest.raises(ValueError):
        parse_members("1234")
