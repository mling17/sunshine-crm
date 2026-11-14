-- CRM v2_022 -> v2_023, SQLite one-time update.
-- Back up crm.db before execution. Run only when schema_migrations has no v2_023.
BEGIN IMMEDIATE;

ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE leads ADD COLUMN created_by INTEGER;

CREATE TABLE IF NOT EXISTS api_tokens (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  token       TEXT NOT NULL UNIQUE,
  user_id     INTEGER NOT NULL,
  expires_at  TEXT,
  revoked_at  TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  create_time TEXT NOT NULL DEFAULT '',
  update_time TEXT NOT NULL DEFAULT '',
  is_delete   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id);

INSERT OR IGNORE INTO dict_items
  (dict_code, key, label, sort, enabled, created_at, updated_at)
VALUES
  ('customer_source', 'api', 'API', 7, 1, datetime('now'), datetime('now'));

INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)
VALUES ('v2_023', datetime('now'), '外部 API Token、用户启用状态与线索创建人');

PRAGMA user_version = 22;
COMMIT;
