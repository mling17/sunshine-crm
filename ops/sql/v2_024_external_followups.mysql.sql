-- CRM v2_023 -> v2_024, MySQL 8 one-time update.
-- Back up the database before execution. Run only when schema_migrations has no v2_024.
START TRANSACTION;

ALTER TABLE `follow_ups`
  ADD COLUMN `created_by` BIGINT UNSIGNED;

INSERT IGNORE INTO `schema_migrations` (`version`, `applied_at`, `note`)
VALUES ('v2_024', UTC_TIMESTAMP(), '外部跟进与创建人审计');

COMMIT;
