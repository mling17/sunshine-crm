-- CRM v2_022 -> v2_023, MySQL 8 one-time update.
-- Back up the database before execution. Run only when schema_migrations has no v2_023.
START TRANSACTION;

ALTER TABLE `users`
  ADD COLUMN `is_active` TINYINT NOT NULL DEFAULT 1;

ALTER TABLE `leads`
  ADD COLUMN `created_by` BIGINT UNSIGNED;

CREATE TABLE IF NOT EXISTS `api_tokens` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(128) NOT NULL,
  `token` VARCHAR(512) NOT NULL,
  `user_id` BIGINT UNSIGNED NOT NULL,
  `expires_at` VARCHAR(32),
  `revoked_at` VARCHAR(32),
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `create_time` VARCHAR(32) NOT NULL DEFAULT '',
  `update_time` VARCHAR(32) NOT NULL DEFAULT '',
  `is_delete` TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_api_tokens_token` (`token`),
  KEY `idx_api_tokens_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `dict_items`
  (`dict_code`, `key`, `label`, `sort`, `enabled`, `created_at`, `updated_at`)
VALUES
  ('customer_source', 'api', 'API', 7, 1, UTC_TIMESTAMP(), UTC_TIMESTAMP());

INSERT IGNORE INTO `schema_migrations` (`version`, `applied_at`, `note`)
VALUES ('v2_023', UTC_TIMESTAMP(), '外部 API Token、用户启用状态与线索创建人');

COMMIT;
