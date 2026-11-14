-- CRM v2_023 -> v2_024, SQLite one-time update.
-- Back up crm.db before execution. Run only when schema_migrations has no v2_024.
BEGIN IMMEDIATE;

ALTER TABLE follow_ups ADD COLUMN created_by INTEGER;

INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)
VALUES ('v2_024', datetime('now'), '外部跟进与创建人审计');

PRAGMA user_version = 23;
COMMIT;
