CREATE TABLE IF NOT EXISTS members (
  discord_id TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  balance    INTEGER NOT NULL DEFAULT 0,
  queue_pos  INTEGER,                          -- NULL kalau sedang main
  status     TEXT NOT NULL CHECK (status IN ('queued', 'active'))
);

CREATE TABLE IF NOT EXISTS sessions (          -- tawaran dan sesi main dalam satu tabel
  id         INTEGER PRIMARY KEY,
  member_id  TEXT NOT NULL REFERENCES members(discord_id),
  status     TEXT NOT NULL CHECK (status IN ('offered', 'active', 'ended')),
  offered_at TEXT,                             -- terisi saat status 'offered'
  started_at TEXT,                             -- terisi saat Accept
  ends_at    TEXT,                             -- terisi saat Accept
  days       INTEGER,                          -- 7 + saldo yang dipakai
  offer_reminded  INTEGER NOT NULL DEFAULT 0,  -- pengingat 12 jam sudah dikirim
  expiry_reminded INTEGER NOT NULL DEFAULT 0   -- pengingat sisa <=1 hari sudah dikirim
);

-- pengaman: maksimal satu pemegang aktif dan satu tawaran berjalan
CREATE UNIQUE INDEX IF NOT EXISTS one_active  ON sessions(status) WHERE status = 'active';
CREATE UNIQUE INDEX IF NOT EXISTS one_offered ON sessions(status) WHERE status = 'offered';
