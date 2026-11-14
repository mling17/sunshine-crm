-- CRM v2_024 -> v2_025, SQLite one-time update.
-- Back up crm.db before execution. Run only when schema_migrations has no v2_025.
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS api_idempotency_records (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  token_id          INTEGER NOT NULL,
  endpoint          TEXT NOT NULL,
  idempotency_key   TEXT NOT NULL,
  request_hash      TEXT NOT NULL,
  response_status   INTEGER,
  response_body     TEXT,
  expires_at        TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  create_time       TEXT NOT NULL DEFAULT '',
  update_time       TEXT NOT NULL DEFAULT '',
  is_delete         INTEGER NOT NULL DEFAULT 0,
  UNIQUE(token_id, endpoint, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_api_idempotency_expires
  ON api_idempotency_records(expires_at);

INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)
VALUES ('v2_025', datetime('now'), '外部写接口幂等重试');

PRAGMA user_version = 24;
COMMIT;
