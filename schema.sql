-- World Cup 2026 Pick-'Ems — D1 (SQLite) schema
-- Apply locally:   wrangler d1 execute wc2026 --local  --file=schema.sql
-- Apply to remote: wrangler d1 execute wc2026 --remote --file=schema.sql

CREATE TABLE IF NOT EXISTS submissions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at   TEXT    NOT NULL,   -- ISO timestamp (server-set)
  slug         TEXT,               -- short share code, e.g. "Xa9k2" → /p/Xa9k2
  name         TEXT,               -- full name (private; never returned by the API)
  display_name TEXT,               -- "fernandof" handle (public)
  email        TEXT,               -- private; never returned by the API
  country      TEXT,               -- "United States" | "Outside the United States"
  lang         TEXT,               -- "en" | "pt"
  payload      TEXT    NOT NULL,   -- full answers JSON (email stripped; also carries the
                                   -- "hidden from leaderboard" flag, so no separate column)
  ip_hash      TEXT                -- salted hash of submitter IP (light abuse signal only)
);

CREATE INDEX        IF NOT EXISTS idx_submissions_created ON submissions (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_slug    ON submissions (slug);

-- MIGRATION for a DB created before slugs existed (only `slug` ever needed a column;
-- the leaderboard "hidden" flag rides inside the payload JSON, so no migration for it):
--   ALTER TABLE submissions ADD COLUMN slug TEXT;
--   CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_slug ON submissions (slug);
