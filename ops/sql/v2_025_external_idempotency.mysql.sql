-- CRM v2_024 -> v2_025, MySQL 8 one-time update.
-- Back up the database before execution. Run only when schema_migrations has no v2_025.
START TRANSACTION;

CREATE TABLE IF NOT EXISTS `api_idempotency_records` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `token_id` BIGINT UNSIGNED NOT NULL,
  `endpoint` VARCHAR(255) NOT NULL,
  `idempotency_key` VARCHAR(255) NOT NULL,
  `request_hash` CHAR(64) NOT NULL,
  `response_status` INT,
  `response_body` LONGTEXT,
  `expires_at` VARCHAR(32) NOT NULL,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `create_time` VARCHAR(32) NOT NULL DEFAULT '',
  `update_time` VARCHAR(32) NOT NULL DEFAULT '',
  `is_delete` TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_api_idempotency_scope`
    (`token_id`, `endpoint`, `idempotency_key`),
  KEY `idx_api_idempotency_expires` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `schema_migrations` (`version`, `applied_at`, `note`)
VALUES ('v2_025', UTC_TIMESTAMP(), '外部写接口幂等重试');

COMMIT;
