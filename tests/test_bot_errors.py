"""The Discord layer must never leave a user with a bare "interaction failed"."""

import asyncio

from discord import app_commands

from bot.config import Settings
from bot.main import QueueBot, _respond
from bot.present import INTERNAL_ERROR


class FakeResponse:
    def __init__(self, done: bool = False):
        self.done = done
        self.messages = []

    def is_done(self) -> bool:
        return self.done

    async def send_message(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))
        self.done = True


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))


class FakeInteraction:
    def __init__(self, done: bool = False):
        self.response = FakeResponse(done=done)
        self.followup = FakeFollowup()
        self.command = None


def make_bot() -> QueueBot:
    return QueueBot(
        Settings(
            token="test",
            guild_id=1,
            notify_channel_id=2,
            admin_role_id=None,
            members=[("1", "a")],
            db_path=":memory:",
        )
    )


def test_respond_uses_followup_after_the_response_was_used():
    interaction = FakeInteraction(done=True)
    asyncio.run(_respond(interaction, "halo", ephemeral=True))
    assert interaction.followup.messages == [("halo", True)]
    assert interaction.response.messages == []


def test_tree_error_replies_ephemeral_instead_of_staying_silent():
    interaction = FakeInteraction()

    class FakeCommand:
        name = "status"
        qualified_name = "status"

    error = app_commands.CommandInvokeError(FakeCommand(), RuntimeError("boom"))
    asyncio.run(make_bot().on_tree_error(interaction, error))
    assert interaction.response.messages == [(INTERNAL_ERROR, True)]
