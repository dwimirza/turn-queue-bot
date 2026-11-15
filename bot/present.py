"""Indonesian text for slash-command replies and the offer message."""

from datetime import datetime

import discord

from bot.timefmt import fmt_wib, remaining
from core.turns import BASE_DAYS

NOT_A_MEMBER = "Kamu bukan anggota antrian"
NOT_YOUR_OFFER = "Bukan tawaran untukmu, atau sudah diproses."
NOT_HOLDER = "Kamu sedang tidak memegang akses."
NOT_ADMIN = "Kamu tidak punya izin."
INTERNAL_ERROR = "Ada error di bot. Coba lagi, atau cek log kalau berulang."
ALREADY_RUNNING = "sudah berjalan"
RESET_PROMPT = "Reset antrian? Semua sesi ditutup, urutan balik ke awal, saldo jadi 0."
RESET_DONE = "Antrian di-reset. Semua kembali ke urutan awal, saldo 0."
RESET_CANCELLED = "Dibatalkan, tidak ada yang berubah."
RESET_NOT_YOURS = "Ini bukan konfirmasi untukmu."


def offer_embed(days: int, balance: int) -> discord.Embed:
    return discord.Embed(
        title="Giliran kamu",
        description=(
            f"Accept: kamu main **{days} hari** (7 + saldo {balance}).\n"
            "Skip: ke belakang antrian, saldo **+7**. Tidak ada yang dipotong."
        ),
    )


def offer_reminder_text(discord_id: str) -> str:
    return (
        f"<@{discord_id}> tawaran kamu belum dijawab. "
        "Kalau lewat 24 jam, otomatis pindah ke belakang antrian tanpa +7."
    )


def expiry_reminder_text(discord_id: str, left: str) -> str:
    return (
        f"<@{discord_id}> sesi kamu sisa **{left}**. "
        "Kalau mau selesai lebih awal, pakai `/checkout` supaya sisanya masuk saldo."
    )


def status_embed(snap: dict, now: datetime) -> discord.Embed:
    holder = snap["holder"]
    offered = snap["offered"]
    balances = snap["balances"]
    embed = discord.Embed(title="Status giliran")
    if holder is None and offered is None:
        embed.description = "Antrian belum jalan. Belum ada yang pegang akses."

    if holder is None:
        embed.add_field(name="Yang main", value="Tidak ada", inline=False)
    else:
        ends = holder["ends_at"]
        embed.add_field(
            name="Yang main",
            value=(
                f"<@{holder['discord_id']}> ({holder['name']})\n"
                f"Sisa {remaining(ends, now)}\n"
                f"Sampai {fmt_wib(ends)}"
            ),
            inline=False,
        )

    if offered is None:
        embed.add_field(name="Tawaran", value="Tidak ada", inline=False)
    else:
        allotment = BASE_DAYS + balances.get(offered["name"], 0)
        balance = balances.get(offered["name"], 0)
        embed.add_field(
            name="Tawaran",
            value=(
                f"<@{offered['discord_id']}> ({offered['name']}) belum jawab\n"
                f"Jatah {allotment} hari ({BASE_DAYS} + cadangan {balance})"
            ),
            inline=False,
        )

    # The offered person is already shown in the "Tawaran" field; don't list them twice.
    queue = snap["queue"]
    if offered is not None:
        queue = [item for item in queue if item["discord_id"] != offered["discord_id"]]
    if queue:
        lines = [_queue_line(i, item) for i, item in enumerate(queue, start=1)]
        embed.add_field(name="Antrian", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Antrian", value="Kosong", inline=False)

    saldo = ", ".join(f"{name} {days}" for name, days in balances.items()) or "—"
    embed.add_field(
        name="Cadangan",
        value=f"{saldo}\nJatah tiap giliran = {BASE_DAYS} + cadangan",
        inline=False,
    )
    return embed


def _queue_line(position: int, item: dict) -> str:
    allotment = BASE_DAYS + item["balance"]
    extra = f" ({item['balance']} cadangan)" if item["balance"] else ""
    return f"{position}. {item['name']} — {allotment} hari{extra} — mulai {fmt_wib(item['eta'])}"
