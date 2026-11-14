-- CRM v2_022 -> v2_025 consolidated production update, SQLite.
-- Back up crm.db first. Run this one-time script only when:
--   PRAGMA user_version = 21 AND schema_migrations has no v2_023/v2_024/v2_025.
-- The script is intentionally non-rerunnable; stop on the first error and restore
-- the backup if transaction completion cannot be confirmed.
BEGIN IMMEDIATE;

ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE leads ADD COLUMN created_by INTEGER;
ALTER TABLE follow_ups ADD COLUMN created_by INTEGER;

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

CREATE TRIGGER "trg_std_api_tokens_ai"
AFTER INSERT ON "api_tokens"
BEGIN
  UPDATE "api_tokens"
  SET create_time = CASE
        WHEN create_time = '' THEN COALESCE(NULLIF(NEW.created_at, ''),
          strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ELSE create_time END,
      update_time = CASE
        WHEN update_time = '' THEN COALESCE(NULLIF(NEW.updated_at, ''),
          NULLIF(NEW.created_at, ''), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ELSE update_time END
  WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER "trg_std_api_tokens_au"
AFTER UPDATE ON "api_tokens"
WHEN NEW.update_time = OLD.update_time
BEGIN
  UPDATE "api_tokens"
  SET update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
  WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER "trg_std_api_idempotency_records_ai"
AFTER INSERT ON "api_idempotency_records"
BEGIN
  UPDATE "api_idempotency_records"
  SET create_time = CASE
        WHEN create_time = '' THEN COALESCE(NULLIF(NEW.created_at, ''),
          strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ELSE create_time END,
      update_time = CASE
        WHEN update_time = '' THEN COALESCE(NULLIF(NEW.updated_at, ''),
          NULLIF(NEW.created_at, ''), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ELSE update_time END
  WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER "trg_std_api_idempotency_records_au"
AFTER UPDATE ON "api_idempotency_records"
WHEN NEW.update_time = OLD.update_time
BEGIN
  UPDATE "api_idempotency_records"
  SET update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
  WHERE rowid = NEW.rowid;
END;

INSERT OR IGNORE INTO dict_items
  (dict_code, key, label, sort, enabled, created_at, updated_at)
VALUES
  ('customer_source', 'api', 'API', 7, 1, datetime('now'), datetime('now'));

INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)
VALUES ('v2_023', datetime('now'), '外部 API Token、用户启用状态与线索创建人');
INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)
VALUES ('v2_024', datetime('now'), '外部跟进与创建人审计');
INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)
VALUES ('v2_025', datetime('now'), '外部写接口幂等重试');

PRAGMA user_version = 24;
COMMIT;
