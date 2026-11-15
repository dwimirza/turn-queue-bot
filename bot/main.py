"""Discord layer. Game rules stay in core.turns; this file only calls them and renders."""

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import tasks

from core import turns
from core.db import connect
from bot.config import Settings, load_settings
from bot.present import (
    ALREADY_RUNNING,
    INTERNAL_ERROR,
    NOT_ADMIN,
    NOT_A_MEMBER,
    NOT_HOLDER,
    NOT_YOUR_OFFER,
    RESET_CANCELLED,
    RESET_DONE,
    RESET_NOT_YOURS,
    RESET_PROMPT,
    expiry_reminder_text,
    offer_embed,
    offer_reminder_text,
    status_embed,
)
from bot.timefmt import fmt_wib, remaining

log = logging.getLogger(__name__)

# Only ping real users: a typo in config can never turn into @everyone / @here.
SAFE_MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False)


def _bot(interaction: discord.Interaction) -> "QueueBot":
    client = interaction.client
    if not isinstance(client, QueueBot):
        raise RuntimeError("interaction is not from QueueBot")
    return client


def _is_member(db, discord_id: str) -> bool:
    return db.execute("SELECT 1 FROM members WHERE discord_id=?", (discord_id,)).fetchone() is not None


def _is_admin(interaction: discord.Interaction) -> bool:
    settings = _bot(interaction).settings
    if settings.admin_role_id is None:
        return bool(interaction.permissions.manage_guild)
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    return any(role.id == settings.admin_role_id for role in member.roles)


async def _respond(interaction: discord.Interaction, content: str, *, ephemeral: bool = False) -> None:
    """Reply without ever letting a failed reply escape (state may already be committed)."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except discord.HTTPException:
        log.warning("could not reply to an interaction", exc_info=True)


class OfferView(discord.ui.View):
    """Persistent Accept / Skip buttons. The target is whoever clicks."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="offer:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _on_accept(interaction)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, custom_id="offer:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _on_skip(interaction)


class ResetConfirm(discord.ui.View):
    """Ephemeral confirm for /admin reset. Not persistent (times out after 60s)."""

    def __init__(self, owner_id: int):
        super().__init__(timeout=60)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(RESET_NOT_YOURS, ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ya, reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = _bot(interaction)
        with bot.db:
            turns.reset(bot.db, bot.settings.members)
        await interaction.response.edit_message(content=RESET_DONE, view=None)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=RESET_CANCELLED, view=None)


async def _notify_channel(bot: "QueueBot") -> discord.abc.Messageable:
    channel = bot.get_channel(bot.settings.notify_channel_id)
    if channel is None:
        channel = await bot.fetch_channel(bot.settings.notify_channel_id)
    return channel


async def notify(bot: "QueueBot", member_id: str) -> None:
    """Post an offer after the DB transaction has committed. Log and continue on failure."""
    try:
        row = bot.db.execute(
            "SELECT balance FROM members WHERE discord_id=?", (member_id,)
        ).fetchone()
        if row is None:
            log.error("notify: unknown member %s", member_id)
            return
        channel = await _notify_channel(bot)
        days = turns.BASE_DAYS + row["balance"]
        await channel.send(
            content=f"<@{member_id}>",
            embed=offer_embed(days, row["balance"]),
            view=OfferView(),
            allowed_mentions=SAFE_MENTIONS,
        )
    except Exception:
        log.exception("failed to send offer to %s", member_id)


async def send_reminder(bot: "QueueBot", kind: str, member_id: str, now: datetime) -> None:
    """Send one reminder. Ticks must not die because a message failed."""
    try:
        channel = await _notify_channel(bot)
        if kind == "offer_halfway":
            text = offer_reminder_text(member_id)
        else:
            row = bot.db.execute(
                "SELECT ends_at FROM sessions WHERE member_id=? AND status='active'",
                (member_id,),
            ).fetchone()
            if row is None:
                return
            text = expiry_reminder_text(member_id, remaining(row["ends_at"], now))
        await channel.send(text, allowed_mentions=SAFE_MENTIONS)
    except Exception:
        log.exception("failed to send %s reminder to %s", kind, member_id)


async def _on_accept(interaction: discord.Interaction) -> None:
    bot = _bot(interaction)
    uid = str(interaction.user.id)
    try:
        # No await inside the transaction: one event = one atomic commit.
        with bot.db:
            days = turns.accept(bot.db, uid)
            ends_at = bot.db.execute(
                "SELECT ends_at FROM sessions WHERE member_id=? AND status='active'",
                (uid,),
            ).fetchone()["ends_at"]
    except turns.NotAllowed:
        await interaction.response.send_message(NOT_YOUR_OFFER, ephemeral=True)
        return
    try:
        await interaction.response.edit_message(
            content=f"<@{uid}> main {days} hari, sampai {fmt_wib(ends_at)}.",
            embed=None,
            view=None,
        )
    except discord.HTTPException:
        log.warning("accept committed but the offer message could not be edited", exc_info=True)


async def _on_skip(interaction: discord.Interaction) -> None:
    bot = _bot(interaction)
    uid = str(interaction.user.id)
    try:
        with bot.db:
            nxt = turns.skip(bot.db, uid)
    except turns.NotAllowed:
        await interaction.response.send_message(NOT_YOUR_OFFER, ephemeral=True)
        return
    try:
        await interaction.response.edit_message(
            content=f"<@{uid}> skip. Saldo +7, ke belakang antrian.",
            embed=None,
            view=None,
        )
    except discord.HTTPException:
        log.warning("skip committed but the offer message could not be edited", exc_info=True)
    if nxt:
        await notify(bot, nxt)


@app_commands.command(name="status", description="Lihat siapa yang main, antrian, dan saldo")
async def status_command(interaction: discord.Interaction):
    bot = _bot(interaction)
    uid = str(interaction.user.id)
    if not _is_member(bot.db, uid):
        await interaction.response.send_message(NOT_A_MEMBER, ephemeral=True)
        return
    now = datetime.now(timezone.utc)
    snap = turns.status(bot.db, now)
    await interaction.response.send_message(embed=status_embed(snap, now))


@app_commands.command(name="checkout", description="Selesai lebih awal, sisa hari masuk saldo")
async def checkout_command(interaction: discord.Interaction):
    bot = _bot(interaction)
    uid = str(interaction.user.id)
    if not _is_member(bot.db, uid):
        await interaction.response.send_message(NOT_A_MEMBER, ephemeral=True)
        return
    try:
        with bot.db:
            before = bot.db.execute(
                "SELECT balance FROM members WHERE discord_id=?", (uid,)
            ).fetchone()["balance"]
            nxt = turns.checkout(bot.db, uid)
            after = bot.db.execute(
                "SELECT balance FROM members WHERE discord_id=?", (uid,)
            ).fetchone()["balance"]
    except turns.NotAllowed:
        await interaction.response.send_message(NOT_HOLDER, ephemeral=True)
        return
    await _respond(interaction, f"Checkout. {after - before} hari masuk saldo.")
    if nxt:
        await notify(bot, nxt)


class Admin(app_commands.Group):
    def __init__(self):
        super().__init__(name="admin", description="Perintah admin antrian")

    @app_commands.command(name="start", description="Mulai antrian dan tawarkan ke orang terdepan")
    async def start(self, interaction: discord.Interaction):
        bot = _bot(interaction)
        if not _is_admin(interaction):
            await interaction.response.send_message(NOT_ADMIN, ephemeral=True)
            return
        with bot.db:
            first = turns.start(bot.db)
        if first is None:
            await interaction.response.send_message(ALREADY_RUNNING, ephemeral=True)
            return
        await _respond(interaction, "Giliran dimulai.")
        await notify(bot, first)

    @app_commands.command(name="reset", description="Reset antrian ke kondisi awal (admin)")
    async def reset(self, interaction: discord.Interaction):
        bot = _bot(interaction)
        if not _is_admin(interaction):
            await interaction.response.send_message(NOT_ADMIN, ephemeral=True)
            return
        await interaction.response.send_message(
            RESET_PROMPT, view=ResetConfirm(interaction.user.id), ephemeral=True
        )


class QueueBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self.on_tree_error
        self.db = None
        guild = discord.Object(id=settings.guild_id)
        self.tree.add_command(status_command, guild=guild)
        self.tree.add_command(checkout_command, guild=guild)
        self.tree.add_command(Admin(), guild=guild)

    async def setup_hook(self):
        self.db = connect(self.settings.db_path)
        with self.db:
            turns.seed_members(self.db, self.settings.members)
        log.info("database ready at %s", self.settings.db_path)
        self.add_view(OfferView())
        guild = discord.Object(id=self.settings.guild_id)
        synced = await self.tree.sync(guild=guild)
        log.info("synced %s commands to guild %s", len(synced), self.settings.guild_id)
        self.tick_loop.start()

    async def on_tree_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Never leave a user with a silent "interaction failed"."""
        original = getattr(error, "original", error)
        command = getattr(interaction.command, "qualified_name", "?")
        log.error("command /%s failed", command, exc_info=original)
        await _respond(interaction, INTERNAL_ERROR, ephemeral=True)

    async def close(self):
        if self.tick_loop.is_running():
            self.tick_loop.cancel()
        await super().close()
        if self.db is not None:
            self.db.close()

    @tasks.loop(seconds=60)
    async def tick_loop(self):
        try:
            await self.wait_until_ready()
            now = datetime.now(timezone.utc)
            with self.db:
                newly = turns.tick(self.db, now)
                reminders = turns.due_reminders(self.db, now)
            for member_id in newly:
                await notify(self, member_id)
            for kind, member_id in reminders:
                await send_reminder(self, kind, member_id, now)
        except Exception:
            log.exception("tick failed")


def main() -> None:
    discord.utils.setup_logging(level=logging.INFO)
    log.info("starting turn queue bot")
    settings = load_settings()
    try:
        QueueBot(settings).run(settings.token, log_handler=None)
    except discord.LoginFailure:
        log.error("DISCORD_TOKEN was rejected; reset it in the Developer Portal and update .env")
        raise SystemExit(1) from None
    except discord.PrivilegedIntentsRequired:
        log.error("privileged intents are enabled for this app; this bot needs none")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
