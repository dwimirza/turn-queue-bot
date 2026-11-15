import pytest

from bot.config import _int_env, parse_members


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


def test_parse_members_rejects_non_numeric_id():
    # A typo like "@everyone" must not reach a `<@...>` mention.
    with pytest.raises(ValueError):
        parse_members("@everyone:dzikra")


def test_parse_members_rejects_duplicate_id():
    with pytest.raises(ValueError):
        parse_members("1:dzikra,1:locke")


def test_int_env_requires_positive_id():
    assert _int_env("GUILD_ID", " 42 ") == 42
    with pytest.raises(SystemExit):
        _int_env("GUILD_ID", "abc")
    with pytest.raises(SystemExit):
        _int_env("GUILD_ID", "0")
