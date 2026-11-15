# Turn Queue Bot

Bot Discord untuk **berbagi satu akses game (GTA 6)** di antara 4 orang dengan sistem **antrian giliran**, bukan kalender.

Satu giliran = **7 hari**, ditambah **cadangan hari** yang menumpuk dari skip atau selesai lebih awal. Semua state disimpan di SQLite, jadi bot aman di-restart kapan saja. Waktu ditampilkan dalam **WIB**.

Spesifikasi lengkap ada di [`SPEC.md`](SPEC.md) — itu sumber kebenaran untuk aturan dan scope.

## Fitur

- **Antrian, bukan jadwal** — urutan orang ditentukan `queue_pos`, bukan tanggal.
- **Tawaran dengan tombol** — orang terdepan ditawari lewat pesan berisi tombol **Accept** / **Skip**.
- **Hari otomatis** — sesi berakhir sendiri saat waktunya habis, tanpa job harian.
- **Cadangan hari** — skip memberi +7, checkout menyimpan sisa hari (dibulatkan ke bawah). Tidak ada batas maksimal.
- **Pengingat otomatis** — 12 jam setelah tawaran belum dijawab, dan saat sisa sesi ≤ 1 hari.
- **Tahan restart** — tombol di pesan lama tetap berfungsi, dan sesi yang habis saat bot mati diproses pada tick pertama.
- **Semua di SQLite** — tidak ada timer di memori, tidak ada state yang hilang saat crash.

## Aturan giliran

State selalu salah satu dari: **IDLE** (tidak ada yang pegang akses), **OFFERED** (menunggu jawaban), **ACTIVE** (ada yang main sampai `ends_at`).

| Kejadian | Efek |
|---|---|
| `/admin start` (hanya saat IDLE) | Tawaran dikirim ke orang terdepan di antrian |
| **Accept** (hanya oleh yang ditawari) | Main `7 + cadangan` hari, cadangan jadi 0, orang itu keluar dari antrian |
| **Skip** (hanya oleh yang ditawari) | Cadangan +7, pindah ke belakang antrian, tidak ada yang dipotong |
| `/checkout` (hanya oleh pemegang akses) | Sisa hari (dibulatkan ke bawah) masuk cadangan, pemegang pindah ke belakang antrian |
| Waktu sesi habis | Sama seperti checkout, tapi dengan 0 hari tersisa |
| Tawaran tidak dijawab 24 jam | Pindah ke belakang antrian, **tanpa** +7 |

Catatan penting:

- Cadangan menumpuk tanpa batas dan otomatis dipakai di giliran berikutnya (`Accept` selalu memberi `7 + cadangan`).
- Hanya ada satu sesi ACTIVE dan satu tawaran OFFERED pada satu waktu.
- Tombol hanya untuk **Accept** dan **Skip** — tidak ada `/checkin`, `/join`, `/leave`, atau `/skip`.

## Perintah

| Perintah | Siapa | Fungsi |
|---|---|---|
| `/status` | semua anggota | Lihat pemegang akses, sisa waktu, tawaran berjalan, antrian + estimasi mulai, dan cadangan tiap orang |
| `/checkout` | pemegang akses | Selesai lebih awal; sisa hari masuk cadangan, orang berikutnya ditawari |
| `/admin start` | admin | Mulai antrian dan tawarkan ke orang terdepan |
| `/admin reset` | admin | Reset ke kondisi awal (dengan tombol konfirmasi): semua sesi ditutup, urutan balik ke awal, cadangan 0 |

**Siapa yang dianggap admin?** Anggota dengan role `ADMIN_ROLE_ID`. Kalau variabel itu kosong, siapa pun yang punya izin **Manage Server** dianggap admin.

Bukan anggota antrian (`MEMBERS`) yang memakai perintah akan mendapat balasan ephemeral "Kamu bukan anggota antrian".

### Tombol Accept / Skip

Muncul di pesan tawaran. Tombolnya hanya bekerja untuk **orang yang sedang ditawari** — orang lain yang mengklik akan dapat pesan ephemeral "Bukan tawaran untukmu, atau sudah diproses.", dan state tidak berubah. Klik dua kali berturut-turut juga aman: klik kedua ditolak.

Tombol tetap berfungsi setelah bot di-restart, selama pesannya belum dihapus.

### Contoh `/status`

```
Status giliran

Yang main
@dzikra (dzikra)
Sisa 5 hari 3 jam
Sampai Sen 23 Nov, 10:00 WIB

Tawaran
Tidak ada

Antrian
1. locke — 14 hari (7 cadangan) — mulai Sen 23 Nov, 10:00 WIB
2. radrtma — 7 hari — mulai Sen 30 Nov, 10:00 WIB
3. kjaer — 7 hari — mulai Sen 7 Dec, 10:00 WIB

Cadangan
dzikra 0, locke 7, radrtma 0, kjaer 5
Jatah tiap giliran = 7 + cadangan
```

Angka "14 hari" berarti orang itu akan main 7 hari dasar + 7 hari cadangan saat gilirannya tiba.

## Pengingat otomatis

Dikirim ke channel notifikasi, masing-masing hanya sekali per sesi:

| Pengingat | Kapan |
|---|---|
| Tawaran belum dijawab | 12 jam setelah tawaran dikirim. Kalau lewat 24 jam, giliran otomatis pindah ke belakang tanpa +7 |
| Sesi hampir habis | Saat sisa waktu ≤ 1 hari, supaya bisa `/checkout` kalau mau menyimpan sisanya |

## Setup

### 1. Prasyarat

- Python **3.11+**
- Sebuah server Discord dan channel teks untuk pesan tawaran (mis. `#giliran`)
- 4 orang yang sudah ada di server tersebut (mereka harus bisa melihat channel notifikasi)

### 2. Install

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Kalau `Activate.ps1` ditolak karena `running scripts is disabled`, langsung pakai `.venv\Scripts\python.exe -m ...` seperti di atas, atau jalankan `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` lalu `. .\.venv\Scripts\Activate.ps1`.

### 3. Buat bot Discord

1. Buka https://discord.com/developers/applications → **New Application**.
2. Tab **Bot** → **Reset Token** → salin token (hanya ditampilkan sekali). Ini `DISCORD_TOKEN`.
3. **Privileged Gateway Intents**: biarkan semuanya **off** — bot ini tidak butuh Message Content atau Server Members.
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`, permissions `View Channels`, `Send Messages`, `Embed Links`. Buka URL hasilnya dan undang bot ke server.

### 4. Ambil ID Discord

Aktifkan **User Settings → Advanced → Developer Mode**, lalu:

| Nilai | Cara |
|---|---|
| `GUILD_ID` | Klik kanan ikon server → Copy Server ID |
| `NOTIFY_CHANNEL_ID` | Klik kanan channel → Copy Channel ID (atau Copy Link, angka kedua di URL) |
| `MEMBERS` | Klik kanan tiap orang → Copy User ID (ID angka, bukan username) |
| `ADMIN_ROLE_ID` | Server Settings → Roles → klik kanan role → Copy Role ID (opsional) |

### 5. Isi `.env`

Salin `.env.example` menjadi `.env` di root repo:

```ini
DISCORD_TOKEN=token-bot-kamu
GUILD_ID=123456789012345678
NOTIFY_CHANNEL_ID=123456789012345678
ADMIN_ROLE_ID=
MEMBERS=111111111111111111:dzikra,222222222222222222:locke,333333333333333333:radrtma,444444444444444444:kjaer
DB_PATH=queue.db
```

- `MEMBERS` menentukan **urutan awal antrian** dan nama yang tampil di `/status`. ID harus **angka** (Copy User ID), bukan username; ID ganda atau bukan angka membuat bot menolak start dengan pesan jelas.
- `ADMIN_ROLE_ID` boleh dikosongkan → fallback ke izin Manage Server.
- `DB_PATH` opsional, default `queue.db` (relatif ke folder tempat bot dijalankan). Folder induknya dibuat otomatis kalau belum ada, jadi `DB_PATH=data/queue.db` aman.
- `.env` **jangan pernah di-commit**; sudah masuk `.gitignore`.

### 6. Validasi konfigurasi

```powershell
.venv\Scripts\python.exe -m scripts.check_env
```

Memeriksa token, guild, channel, role admin, dan setiap ID di `MEMBERS` (termasuk apakah mereka benar-benar anggota server). Semua baris harus `[OK]`.

### 7. Jalankan

```powershell
.venv\Scripts\python.exe -m bot.main
```

Saat pertama kali jalan, `queue.db` dibuat otomatis, 4 anggota di-seed sesuai `MEMBERS`, dan slash command disinkronkan ke server (langsung muncul, tanpa menunggu 1 jam).

> Nama dan urutan anggota **tertanam saat seed pertama**. Kalau mau mengubahnya setelah `queue.db` ada, hapus file DB (bot harus berhenti) lalu jalankan ulang, atau pakai `/admin reset` (saldo ikut 0).

## Testing

```powershell
.venv\Scripts\python.exe -m pytest      # unit test aturan antrian, migrasi, tampilan
.venv\Scripts\python.exe -m scripts.sim # simulasi alur lengkap tanpa Discord/token
```

`scripts/sim.py` menjalankan satu putaran penuh (start → accept → checkout → skip → timeout) memakai database sementara, jadi tidak menyentuh `queue.db`.

Untuk menguji perilaku berbasis waktu tanpa menunggu berhari-hari, backdate baris di database saat bot berjalan (tick berjalan tiap 60 detik):

```powershell
# sesi langsung habis
python -c 'import sqlite3; db=sqlite3.connect("queue.db"); db.execute("UPDATE sessions SET ends_at=?", ("2020-01-01T00:00:00+00:00",)); db.commit()'

# tawaran dianggap sudah lewat 24 jam
python -c 'import sqlite3; db=sqlite3.connect("queue.db"); db.execute("UPDATE sessions SET offered_at=?", ("2020-01-01T00:00:00+00:00",)); db.commit()'
```

## Deploy (hidup 24/7)

Bot ini butuh proses yang **hidup terus** dan **disk persisten**. Rekomendasi: **Oracle Cloud Always Free**, region **Singapore**, shape **VM.Standard.E2.1.Micro** (1/8 OCPU, 1 GB RAM) — lebih dari cukup, dan gratis permanen. Alternatif gratis lain: GCP `e2-micro` di `us-west1` (jarak ~0,25 detik, tidak masalah untuk bot ini). Kalau tidak mau berurusan dengan free tier: VPS Singapura ~$3–4/bulan.

### Docker (cara utama)

```bash
git clone https://github.com/dwimirza/turn-queue-bot.git
cd turn-queue-bot
cp .env.example .env
nano .env          # isi token + ID Discord
chmod 600 .env

docker compose up -d --build
docker compose logs -f
```

Yang dilakukan compose:

- `queue.db` disimpan di named volume `queue-data` (path di container: `/data/queue.db`), jadi data selamat saat container dibuat ulang.
- `restart: unless-stopped` — bot hidup lagi otomatis setelah VM reboot atau crash.
- Log dibatasi 10 MB × 3 file supaya disk tidak penuh.
- `.env` tidak pernah masuk image (lihat `.dockerignore`).

Operasi sehari-hari:

```bash
docker compose logs -f --tail 100     # lihat log
docker compose restart                # restart manual
git pull && docker compose up -d --build   # update ke versi terbaru
docker exec -it turn-queue-bot bash   # masuk ke container
```

### Backup harian

`scripts/backup.py` menyalin database memakai SQLite backup API (aman walau bot sedang menulis) ke `backup/queue-YYYY-MM-DD.db`, dan menyimpan `BACKUP_KEEP_DAYS` hari terakhir (default 14).

```bash
# tambahkan ke crontab -e di VM
0 3 * * * docker exec turn-queue-bot python -m scripts.backup >> ~/queue-backup.log 2>&1
```

Salin backup ke laptop sesekali, karena "gratis selamanya" tetap bisa berakhir:

```bash
docker cp turn-queue-bot:/data/backup ./backup
scp -r ubuntu@<ip-server>:~/turn-queue-bot/backup .
```

### systemd (alternatif tanpa Docker)

Pakai unit yang sudah disediakan, sesuaikan `User=`, `WorkingDirectory=`, dan path venv:

```bash
sudo mkdir -p /opt/turn-queue-bot/data
sudo cp deploy/turn-queue-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now turn-queue-bot
journalctl -u turn-queue-bot -f
```

Unit memakai `Restart=always` dan `DB_PATH=/opt/turn-queue-bot/data/queue.db`.

### Catatan free tier

- Oracle bisa menarik instance yang dianggap idle; bot yang terhubung ke gateway 24/7 biasanya aman, tapi jangan jadikan satu-satunya tempat backup.
- Jangan hapus boot volume saat menghapus instance — data antrian ada di situ.
- Hanya port SSH (22) yang perlu terbuka. Bot tidak menerima koneksi masuk.

## Struktur proyek

```
core/                # aturan main, tanpa import discord
  turns.py           # seluruh transisi state antrian
  db.py              # connect + migrasi
schema.sql           # tabel members & sessions
bot/                 # layer Discord
  main.py            # client, command, tombol, tick loop
  present.py         # semua teks Indonesia
  timefmt.py         # format WIB
  config.py          # .env
scripts/
  check_env.py       # validasi .env ke Discord API
  sim.py             # simulasi aturan tanpa Discord
tests/               # unit test core + tampilan
SPEC.md              # sumber kebenaran requirement
```

`core/` tidak pernah meng-import `discord`, dan Discord layer hanya memanggil fungsi core lalu menampilkan hasilnya.

## Data & backup

- Semua state ada di satu file SQLite (`DB_PATH`, default `queue.db`). Jangan jalankan dua instance bot dengan DB yang sama.
- DB memakai mode **WAL**, jadi `queue.db-wal` dan `queue.db-shm` bisa muncul di sampingnya. Itu normal — jangan dihapus selama bot hidup.
- Backup murah dan aman dilakukan saat bot hidup:

```powershell
sqlite3 queue.db ".backup 'queue-2026-11-15.db'"
```

- Ingin kembali ke kondisi awal: hentikan bot, hapus `queue.db`, jalankan lagi (seed ulang dari `MEMBERS`).

## Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `Missing required env: ...` | `.env` tidak ada atau tidak di root repo; variabel wajib: `DISCORD_TOKEN`, `GUILD_ID`, `NOTIFY_CHANNEL_ID`, `MEMBERS` |
| `401 Unauthorized` saat check_env | Token salah/kedaluwarsa → Reset Token di Developer Portal, perbarui `.env` |
| `404 Unknown Channel` | `NOTIFY_CHANNEL_ID` salah (mungkin menyalin contoh), atau channel sudah dihapus |
| `not in this guild` | Channel dan server berasal dari server berbeda |
| Slash command tidak muncul | Bot belum diundang dengan scope `applications.commands`, atau command belum tersinkron — restart bot dan cek log `synced N commands` |
| Tawaran tidak muncul di channel | Bot tidak punya izin `View Channel` / `Send Messages` / `Embed Links` di channel itu. Errornya hanya tercatat di log |
| Tombol "interaction failed" | Bot sedang mati. Nyalakan lagi; tombol di pesan lama tetap berlaku |
| Error `running scripts is disabled` | Kebijakan PowerShell; pakai `.venv\Scripts\python.exe -m bot.main` atau `Set-ExecutionPolicy -Scope Process Bypass` |
| `/admin start` bilang "sudah berjalan" | Masih ada sesi ACTIVE atau tawaran OFFERED. Tunggu, selesaikan dengan `/checkout`, atau `/admin reset` |
| Data terlihat "hilang" | Bot dijalankan dari folder lain sehingga membuat `queue.db` baru. Selalu jalankan dari root repo atau pakai `DB_PATH` absolut |

Log keluar ke **stderr** lewat `discord.utils.setup_logging` (level INFO), lengkap dengan timestamp dan traceback. Setiap kegagalan pengiriman pesan atau tick dicatat tanpa mematikan bot.
