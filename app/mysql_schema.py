"""MySQL 8.0 定稿表结构。

SQLite 的 V2 迁移链包含 PRAGMA、表重建和 SQLite 触发器，不能直接搬到 MySQL。
这里保存最终结构，应用每次启动幂等执行 ``CREATE TABLE IF NOT EXISTS``；
数据从旧 SQLite 导入时由 ``ops/migrate_sqlite_to_mysql.py`` 负责。

设计约束与项目 AGENT.md 对齐：
- 所有业务表都有 create_time / update_time / is_delete；
- 不创建数据库外键，引用一致性由业务层维护。
"""

from __future__ import annotations

import pymysql
from pymysql.cursors import DictCursor

from app.config.settings import settings


STANDARD_COLUMNS = """
  `create_time` VARCHAR(32) NOT NULL DEFAULT '',
  `update_time` VARCHAR(32) NOT NULL DEFAULT '',
  `is_delete` TINYINT NOT NULL DEFAULT 0
"""


TABLE_DDL: dict[str, str] = {
    "users": """
CREATE TABLE IF NOT EXISTS `users` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(64) NOT NULL,
  `password_hash` TEXT NOT NULL,
  `created_at` VARCHAR(32) NOT NULL,
  `display_name` VARCHAR(64),
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "sessions": """
CREATE TABLE IF NOT EXISTS `sessions` (
  `token` VARCHAR(128) NOT NULL,
  `username` VARCHAR(64) NOT NULL,
  `created_at` VARCHAR(32) NOT NULL,
  `expires_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "customers": """
CREATE TABLE IF NOT EXISTS `customers` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `phone` VARCHAR(64),
  `wechat` VARCHAR(128),
  `location` VARCHAR(500),
  `note` TEXT,
  `customer_type` VARCHAR(32) NOT NULL DEFAULT 'personal',
  `source` VARCHAR(64),
  `source_other` VARCHAR(255),
  `intent_level` VARCHAR(32),
  `company_name` VARCHAR(255),
  `owner` VARCHAR(64),
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `house_type` VARCHAR(128),
  `floor` VARCHAR(64),
  `install_at` VARCHAR(64),
  `decoration_stage` VARCHAR(128),
  `budget` VARCHAR(128),
  `decider` VARCHAR(128),
  `care` TEXT,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_customers_name` (`name`),
  KEY `idx_customers_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "deals": """
CREATE TABLE IF NOT EXISTS `deals` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `customer_id` BIGINT UNSIGNED NOT NULL,
  `product_type` VARCHAR(64),
  `model` VARCHAR(128),
  `spec` VARCHAR(500),
  `amount` DOUBLE NOT NULL DEFAULT 0,
  `deposit` DOUBLE NOT NULL DEFAULT 0,
  `balance` DOUBLE NOT NULL DEFAULT 0,
  `stage` VARCHAR(32) NOT NULL DEFAULT 'lead',
  `closed_at` VARCHAR(32),
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `title` VARCHAR(255),
  `lost_reason` VARCHAR(64),
  `lost_reason_other` VARCHAR(500),
  `source_lost_deal_id` BIGINT UNSIGNED,
  `order_id` BIGINT UNSIGNED,
  `owner` VARCHAR(64),
  `drive_type` VARCHAR(32),
  `note` TEXT,
  `locked_at` VARCHAR(32),
  `product_id` BIGINT UNSIGNED,
  `product_code_snapshot` VARCHAR(64),
  `product_name_snapshot` VARCHAR(255),
  `product_config_snapshot` TEXT,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_deals_customer` (`customer_id`),
  KEY `idx_deals_stage` (`stage`),
  KEY `idx_deals_closed` (`closed_at`),
  KEY `idx_deals_order` (`order_id`),
  KEY `idx_deals_product` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "follow_ups": """
CREATE TABLE IF NOT EXISTS `follow_ups` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `object_type` VARCHAR(32) NOT NULL DEFAULT 'customer',
  `object_id` BIGINT UNSIGNED,
  `customer_id` BIGINT UNSIGNED,
  `deal_id` BIGINT UNSIGNED,
  `method` VARCHAR(32),
  `content` TEXT NOT NULL,
  `next_date` VARCHAR(32),
  `created_at` VARCHAR(32) NOT NULL,
  `kind` VARCHAR(32) NOT NULL DEFAULT 'follow',
  `detail` LONGTEXT,
  `quote_id` BIGINT UNSIGNED,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_fu_object` (`object_type`, `object_id`),
  KEY `idx_fu_customer` (`customer_id`),
  KEY `idx_fu_deal` (`deal_id`),
  KEY `idx_fu_next_date` (`next_date`),
  KEY `idx_fu_kind` (`kind`),
  KEY `idx_fu_quote` (`quote_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "attachments": """
CREATE TABLE IF NOT EXISTS `attachments` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `object_type` VARCHAR(32) NOT NULL DEFAULT 'follow_up',
  `object_id` BIGINT UNSIGNED,
  `follow_up_id` BIGINT UNSIGNED,
  `storage_key` VARCHAR(500) NOT NULL,
  `file_name` VARCHAR(255),
  `mime_type` VARCHAR(128),
  `size` BIGINT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_att_obj` (`object_type`, `object_id`),
  KEY `idx_att_fu` (`follow_up_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "import_log": """
CREATE TABLE IF NOT EXISTS `import_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `source_name` VARCHAR(255) NOT NULL,
  `column_mapping` LONGTEXT,
  `row_count` INT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "tags": """
CREATE TABLE IF NOT EXISTS `tags` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(64) NOT NULL,
  `created_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tags_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "customer_tags": """
CREATE TABLE IF NOT EXISTS `customer_tags` (
  `customer_id` BIGINT UNSIGNED NOT NULL,
  `tag_id` BIGINT UNSIGNED NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`customer_id`, `tag_id`),
  KEY `idx_cust_tag_t` (`tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "leads": """
CREATE TABLE IF NOT EXISTS `leads` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255),
  `phone` VARCHAR(64),
  `wechat` VARCHAR(128),
  `lead_type` VARCHAR(32) NOT NULL DEFAULT 'personal',
  `company_name` VARCHAR(255),
  `source` VARCHAR(64),
  `source_other` VARCHAR(255),
  `location` VARCHAR(500),
  `note` TEXT,
  `intent_level` VARCHAR(32),
  `status` VARCHAR(32) NOT NULL DEFAULT 'new',
  `invalid_reason` VARCHAR(64),
  `invalid_reason_other` VARCHAR(500),
  `converted_customer_id` BIGINT UNSIGNED,
  `converted_deal_id` BIGINT UNSIGNED,
  `owner` VARCHAR(64),
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  `active_phone` VARCHAR(64)
    GENERATED ALWAYS AS (CASE WHEN `is_delete` = 0 THEN `phone` ELSE NULL END) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_leads_phone_active` (`active_phone`),
  KEY `idx_leads_status` (`status`),
  KEY `idx_leads_phone` (`phone`),
  KEY `idx_leads_wechat` (`wechat`),
  KEY `idx_leads_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "lead_tags": """
CREATE TABLE IF NOT EXISTS `lead_tags` (
  `lead_id` BIGINT UNSIGNED NOT NULL,
  `tag_id` BIGINT UNSIGNED NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`lead_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "carriers": """
CREATE TABLE IF NOT EXISTS `carriers` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(128) NOT NULL,
  `code` VARCHAR(64),
  `contact_person` VARCHAR(128),
  `phone` VARCHAR(64),
  `address` VARCHAR(500),
  `is_active` TINYINT NOT NULL DEFAULT 1,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_carriers_name` (`name`),
  KEY `idx_carriers_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "carrier_contacts": """
CREATE TABLE IF NOT EXISTS `carrier_contacts` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `carrier_id` BIGINT UNSIGNED NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `phone` VARCHAR(64) NOT NULL,
  `tags` TEXT,
  `sort` INT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_carrier_contacts` (`carrier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "customer_addresses": """
CREATE TABLE IF NOT EXISTS `customer_addresses` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `customer_id` BIGINT UNSIGNED NOT NULL,
  `label` VARCHAR(128),
  `receiver_name` VARCHAR(128) NOT NULL,
  `phone` VARCHAR(64) NOT NULL,
  `address` VARCHAR(1000) NOT NULL,
  `is_default` TINYINT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_addr_customer` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "orders": """
CREATE TABLE IF NOT EXISTS `orders` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `order_no` VARCHAR(64) NOT NULL,
  `order_name` VARCHAR(255),
  `customer_id` BIGINT UNSIGNED NOT NULL,
  `deal_id` BIGINT UNSIGNED NOT NULL,
  `product_type` VARCHAR(64),
  `model` VARCHAR(128),
  `spec` VARCHAR(500),
  `amount` DOUBLE NOT NULL DEFAULT 0,
  `deposit_paid` DOUBLE NOT NULL DEFAULT 0,
  `balance_paid` DOUBLE NOT NULL DEFAULT 0,
  `logistics_mode` VARCHAR(32),
  `carrier_id` BIGINT UNSIGNED,
  `tracking_no` VARCHAR(128),
  `shipped_at` VARCHAR(32),
  `completed_at` VARCHAR(32),
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending_payment',
  `note` TEXT,
  `owner` VARCHAR(64),
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `deposit_amount` DOUBLE,
  `balance_amount` DOUBLE,
  `logistics_fee` DOUBLE NOT NULL DEFAULT 0,
  `address_id` BIGINT UNSIGNED,
  `receiver_name` VARCHAR(128),
  `receiver_phone` VARCHAR(64),
  `receiver_address` VARCHAR(1000),
  `carrier_contact_id` BIGINT UNSIGNED,
  `carrier_contact_name` VARCHAR(128),
  `carrier_contact_phone` VARCHAR(64),
  `product_id` BIGINT UNSIGNED,
  `product_code_snapshot` VARCHAR(64),
  `product_name_snapshot` VARCHAR(255),
  `product_config_snapshot` TEXT,
  `product_total` DOUBLE NOT NULL DEFAULT 0,
  `discount_amount` DOUBLE NOT NULL DEFAULT 0,
  `discount_reason` VARCHAR(500),
  `product_payable` DOUBLE NOT NULL DEFAULT 0,
  `customer_confirmed_at` VARCHAR(32),
  `customer_confirmation_note` TEXT,
  `quote_id` BIGINT UNSIGNED,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_orders_no` (`order_no`),
  UNIQUE KEY `uq_orders_deal` (`deal_id`),
  KEY `idx_orders_status` (`status`),
  KEY `idx_orders_customer` (`customer_id`),
  KEY `idx_orders_created` (`created_at`),
  KEY `idx_orders_product` (`product_id`),
  KEY `idx_orders_quote` (`quote_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "order_items": """
CREATE TABLE IF NOT EXISTS `order_items` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `order_id` BIGINT UNSIGNED NOT NULL,
  `source_deal_item_id` BIGINT UNSIGNED,
  `source_quote_item_id` BIGINT UNSIGNED,
  `product_id` BIGINT UNSIGNED,
  `product_code_snapshot` VARCHAR(64),
  `product_name_snapshot` VARCHAR(255),
  `product_config_snapshot` TEXT,
  `product_type` VARCHAR(64),
  `model` VARCHAR(128),
  `drive_type` VARCHAR(32),
  `quantity` INT NOT NULL DEFAULT 1,
  `spec` VARCHAR(500),
  `production_spec` TEXT,
  `unit_price` DOUBLE NOT NULL DEFAULT 0,
  `amount` DOUBLE NOT NULL DEFAULT 0,
  `note` TEXT,
  `sort` INT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_order_items_order` (`order_id`, `is_delete`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "order_status_log": """
CREATE TABLE IF NOT EXISTS `order_status_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `order_id` BIGINT UNSIGNED NOT NULL,
  `from_status` VARCHAR(32),
  `to_status` VARCHAR(32) NOT NULL,
  `deposit_paid` DOUBLE,
  `balance_paid` DOUBLE,
  `screenshot_ids` TEXT,
  `logistics_mode` VARCHAR(32),
  `carrier_id` BIGINT UNSIGNED,
  `tracking_no` VARCHAR(128),
  `note` TEXT,
  `created_at` VARCHAR(32) NOT NULL,
  `event_type` VARCHAR(32) NOT NULL DEFAULT 'stage',
  `detail` LONGTEXT,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_osl_order` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "aftersales": """
CREATE TABLE IF NOT EXISTS `aftersales` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `no` VARCHAR(64) NOT NULL,
  `order_id` BIGINT UNSIGNED NOT NULL,
  `customer_id` BIGINT UNSIGNED NOT NULL,
  `type` VARCHAR(32) NOT NULL,
  `type_other` VARCHAR(255),
  `description` TEXT NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `result` TEXT,
  `reject_reason` TEXT,
  `closed_at` VARCHAR(32),
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `related_aftersale_id` BIGINT UNSIGNED,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_aftersales_no` (`no`),
  KEY `idx_as_status` (`status`),
  KEY `idx_as_order` (`order_id`),
  KEY `idx_as_customer` (`customer_id`),
  KEY `idx_as_created` (`created_at`),
  KEY `idx_as_related` (`related_aftersale_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "aftersale_status_log": """
CREATE TABLE IF NOT EXISTS `aftersale_status_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `aftersale_id` BIGINT UNSIGNED NOT NULL,
  `from_status` VARCHAR(32),
  `to_status` VARCHAR(32) NOT NULL,
  `note` TEXT,
  `created_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_asl_aftersale` (`aftersale_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "products": """
CREATE TABLE IF NOT EXISTS `products` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `seed_key` VARCHAR(64) NOT NULL,
  `code` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `category` VARCHAR(64) NOT NULL DEFAULT '天窗',
  `series` VARCHAR(64),
  `structure` VARCHAR(64),
  `opening_mode` VARCHAR(64),
  `drive_type` VARCHAR(32),
  `frame_type` VARCHAR(64),
  `leaf_type` VARCHAR(64),
  `edge_type` VARCHAR(32),
  `leaf_count` INT,
  `min_width` DOUBLE,
  `max_width` DOUBLE,
  `min_height` DOUBLE,
  `max_height` DOUBLE,
  `attributes` LONGTEXT,
  `source_template` VARCHAR(500),
  `form_storage_key` VARCHAR(500),
  `form_file_name` VARCHAR(255),
  `form_file_size` BIGINT NOT NULL DEFAULT 0,
  `form_sha256` VARCHAR(128),
  `form_uploaded_at` VARCHAR(32),
  `description` TEXT,
  `is_active` TINYINT NOT NULL DEFAULT 1,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  `active_code` VARCHAR(64)
    GENERATED ALWAYS AS (CASE WHEN `is_delete` = 0 THEN `code` ELSE NULL END) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_products_seed_key` (`seed_key`),
  UNIQUE KEY `uq_products_code_active` (`active_code`),
  KEY `idx_products_category` (`category`, `series`),
  KEY `idx_products_active` (`is_active`, `is_delete`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "deal_items": """
CREATE TABLE IF NOT EXISTS `deal_items` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `deal_id` BIGINT UNSIGNED NOT NULL,
  `product_id` BIGINT UNSIGNED,
  `product_code_snapshot` VARCHAR(64),
  `product_name_snapshot` VARCHAR(255),
  `product_config_snapshot` TEXT,
  `product_type` VARCHAR(64),
  `model` VARCHAR(128),
  `drive_type` VARCHAR(32),
  `quantity` INT NOT NULL DEFAULT 1,
  `spec` VARCHAR(500),
  `production_spec` TEXT,
  `unit_price` DOUBLE NOT NULL DEFAULT 0,
  `amount` DOUBLE NOT NULL DEFAULT 0,
  `note` TEXT,
  `sort` INT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_deal_items_deal` (`deal_id`, `is_delete`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "deal_tags": """
CREATE TABLE IF NOT EXISTS `deal_tags` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `deal_id` BIGINT UNSIGNED NOT NULL,
  `tag_id` BIGINT UNSIGNED NOT NULL,
  `source` VARCHAR(64) NOT NULL DEFAULT 'manual',
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_deal_tags` (`deal_id`, `tag_id`, `source`),
  KEY `idx_deal_tags_deal` (`deal_id`, `is_delete`),
  KEY `idx_deal_tags_tag` (`tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "deal_quotes": """
CREATE TABLE IF NOT EXISTS `deal_quotes` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `quote_no` VARCHAR(64) NOT NULL,
  `deal_id` BIGINT UNSIGNED NOT NULL,
  `customer_id` BIGINT UNSIGNED NOT NULL,
  `title` VARCHAR(255) NOT NULL,
  `note` TEXT,
  `status` VARCHAR(32) NOT NULL DEFAULT 'draft',
  `amount` DOUBLE NOT NULL DEFAULT 0,
  `confirmed_at` VARCHAR(32),
  `confirmation_note` TEXT,
  `order_id` BIGINT UNSIGNED,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  `confirmed_deal_id` BIGINT UNSIGNED
    GENERATED ALWAYS AS (
      CASE WHEN `status` = 'confirmed' AND `is_delete` = 0 THEN `deal_id` ELSE NULL END
    ) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_deal_quotes_no` (`quote_no`),
  UNIQUE KEY `uq_deal_quotes_confirmed` (`confirmed_deal_id`),
  KEY `idx_deal_quotes_deal` (`deal_id`, `is_delete`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "quote_items": """
CREATE TABLE IF NOT EXISTS `quote_items` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `quote_id` BIGINT UNSIGNED NOT NULL,
  `deal_id` BIGINT UNSIGNED NOT NULL,
  `product_id` BIGINT UNSIGNED NOT NULL,
  `product_code_snapshot` VARCHAR(64),
  `product_name_snapshot` VARCHAR(255),
  `product_config_snapshot` TEXT,
  `product_type` VARCHAR(64),
  `model` VARCHAR(128),
  `drive_type` VARCHAR(32),
  `quantity` INT NOT NULL DEFAULT 1,
  `spec` VARCHAR(500),
  `production_spec` TEXT,
  `unit_price` DOUBLE NOT NULL DEFAULT 0,
  `amount` DOUBLE NOT NULL DEFAULT 0,
  `note` TEXT,
  `form_storage_key` VARCHAR(500),
  `form_file_name` VARCHAR(255),
  `form_file_size` BIGINT NOT NULL DEFAULT 0,
  `form_mime_type` VARCHAR(128),
  `form_sha256` VARCHAR(128),
  `form_content_json` LONGTEXT,
  `sort` INT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `recognized_total` DOUBLE NOT NULL DEFAULT 0,
  `a1_value` TEXT,
  `amount_cell` VARCHAR(64),
  `form_preview_storage_key` VARCHAR(500),
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  KEY `idx_quote_items_quote` (`quote_id`, `is_delete`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "dict_items": """
CREATE TABLE IF NOT EXISTS `dict_items` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `dict_code` VARCHAR(64) NOT NULL,
  `key` VARCHAR(128) NOT NULL,
  `label` VARCHAR(255) NOT NULL,
  `sort` INT NOT NULL DEFAULT 0,
  `enabled` TINYINT NOT NULL DEFAULT 1,
  `meta` LONGTEXT,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dict_items` (`dict_code`, `key`),
  KEY `idx_dict_code` (`dict_code`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "follow_up_phrases": """
CREATE TABLE IF NOT EXISTS `follow_up_phrases` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `object_type` VARCHAR(32) NOT NULL,
  `content` VARCHAR(500) NOT NULL,
  `sort` INT NOT NULL DEFAULT 0,
  `created_at` VARCHAR(32) NOT NULL,
  `updated_at` VARCHAR(32) NOT NULL,
  `${STANDARD}`,
  `active_content` VARCHAR(500)
    GENERATED ALWAYS AS (CASE WHEN `is_delete` = 0 THEN `content` ELSE NULL END) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_follow_phrases_active` (`object_type`, `active_content`),
  KEY `idx_follow_phrases_object` (`object_type`, `is_delete`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "schema_migrations": """
CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `version` VARCHAR(64) NOT NULL,
  `applied_at` VARCHAR(32) NOT NULL,
  `note` TEXT,
  `${STANDARD}`,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "migration_clear_guard": """
CREATE TABLE IF NOT EXISTS `migration_clear_guard` (
  `version` VARCHAR(64) NOT NULL,
  `${STANDARD}`,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
}


def table_ddl() -> list[str]:
    # 所有 DDL 中的 ${STANDARD} 在模块加载前展开，避免动态拼接带来注入面。
    return [
        statement.replace("`${STANDARD}`", STANDARD_COLUMNS).strip()
        for statement in TABLE_DDL.values()
    ]


def _raw_connection(*, autocommit: bool = False):
    return pymysql.connect(
        host=settings.CRM_MYSQL_HOST,
        port=settings.CRM_MYSQL_PORT,
        user=settings.CRM_MYSQL_USER,
        password=settings.CRM_MYSQL_PASSWORD,
        database=settings.CRM_MYSQL_DATABASE,
        charset=settings.CRM_MYSQL_CHARSET,
        cursorclass=DictCursor,
        autocommit=autocommit,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        ssl_disabled=settings.CRM_MYSQL_SSL_DISABLED,
        init_command="SET SESSION time_zone = '+08:00'",
    )


def _column_names(cursor, table: str) -> set[str]:
    cursor.execute(
        "SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS"
        " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,),
    )
    return {str(row["name"]) for row in cursor.fetchall()}


def _drop_redundant_customer_contacts(cursor) -> None:
    """把旧主联系人回写到 customers 后删除冗余表。"""
    cursor.execute(
        "SELECT 1 FROM information_schema.TABLES"
        " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_contacts'"
    )
    if cursor.fetchone() is None:
        return
    cursor.execute(
        """
        UPDATE `customers` c
        JOIN (
          SELECT customer_id, name, phone, wechat,
                 ROW_NUMBER() OVER (
                   PARTITION BY customer_id
                   ORDER BY is_primary DESC, id ASC
                 ) AS row_no
          FROM `customer_contacts`
          WHERE is_delete = 0
        ) cc ON cc.customer_id = c.id
        SET c.company_name = COALESCE(NULLIF(TRIM(cc.name), ''), c.company_name),
            c.phone = COALESCE(NULLIF(TRIM(c.phone), ''), NULLIF(TRIM(cc.phone), '')),
            c.wechat = COALESCE(NULLIF(TRIM(c.wechat), ''), NULLIF(TRIM(cc.wechat), ''))
        WHERE cc.row_no = 1
        """
    )
    cursor.execute("DROP TABLE `customer_contacts`")


def _standard_triggers(table: str, columns: set[str]) -> list[str]:
    now = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"
    created_source = (
        f"COALESCE(NULLIF(NEW.`created_at`, ''), {now})"
        if "created_at" in columns
        else now
    )
    updated_source = (
        f"COALESCE(NULLIF(NEW.`updated_at`, ''), NULLIF(NEW.`created_at`, ''), {now})"
        if "updated_at" in columns and "created_at" in columns
        else (
            f"COALESCE(NULLIF(NEW.`updated_at`, ''), {now})"
            if "updated_at" in columns
            else created_source
        )
    )
    insert_trigger = f"trg_std_{table}_ai"
    update_trigger = f"trg_std_{table}_au"
    return [
        f"DROP TRIGGER IF EXISTS `{insert_trigger}`",
        f"""
CREATE TRIGGER `{insert_trigger}` BEFORE INSERT ON `{table}`
FOR EACH ROW SET
  NEW.`create_time` = IF(NEW.`create_time` = '', {created_source}, NEW.`create_time`),
  NEW.`update_time` = IF(NEW.`update_time` = '', {updated_source}, NEW.`update_time`)
""",
        f"DROP TRIGGER IF EXISTS `{update_trigger}`",
        f"""
CREATE TRIGGER `{update_trigger}` BEFORE UPDATE ON `{table}`
FOR EACH ROW SET
  NEW.`update_time` = IF(
    NEW.`update_time` <=> OLD.`update_time`,
    {now},
    NEW.`update_time`
  )
""",
    ]


def _ensure_order_name(cursor) -> None:
    """补齐既有 MySQL orders 表，并从来源报价单标题回填名称。"""
    if "order_name" not in _column_names(cursor, "orders"):
        cursor.execute("ALTER TABLE `orders` ADD COLUMN `order_name` VARCHAR(255)")
    cursor.execute(
        """
        UPDATE `orders` o
        LEFT JOIN `deal_quotes` q ON q.`id` = o.`quote_id`
        SET o.`order_name` = COALESCE(NULLIF(TRIM(q.`title`), ''), o.`order_no`)
        WHERE o.`order_name` IS NULL OR TRIM(o.`order_name`) = ''
        """
    )


def ensure_mysql_schema() -> None:
    """建最终表结构和项目约定的审计字段触发器（幂等）。"""
    conn = _raw_connection()
    try:
        with conn.cursor() as cursor:
            for statement in table_ddl():
                cursor.execute(statement)
            _drop_redundant_customer_contacts(cursor)
            _ensure_order_name(cursor)
            for table in TABLE_DDL:
                for statement in _standard_triggers(table, _column_names(cursor, table)):
                    cursor.execute(statement)

            cursor.execute("DROP TRIGGER IF EXISTS `trg_fu_object_fill`")
            cursor.execute(
                """
CREATE TRIGGER `trg_fu_object_fill` BEFORE INSERT ON `follow_ups`
FOR EACH ROW
BEGIN
  IF NEW.`object_id` IS NULL AND NEW.`customer_id` IS NOT NULL THEN
    SET NEW.`object_type` = 'customer', NEW.`object_id` = NEW.`customer_id`;
  ELSEIF NEW.`object_id` IS NULL AND NEW.`deal_id` IS NOT NULL THEN
    SET NEW.`object_type` = 'deal', NEW.`object_id` = NEW.`deal_id`;
  END IF;
END
"""
            )
            cursor.execute("DROP TRIGGER IF EXISTS `trg_att_object_fill`")
            cursor.execute(
                """
CREATE TRIGGER `trg_att_object_fill` BEFORE INSERT ON `attachments`
FOR EACH ROW
BEGIN
  IF NEW.`object_id` IS NULL AND NEW.`follow_up_id` IS NOT NULL THEN
    SET NEW.`object_type` = 'follow_up', NEW.`object_id` = NEW.`follow_up_id`;
  END IF;
END
"""
            )

            # 项目规则禁止数据库外键；为兼容既有 SQLite 的级联语义，
            # 在 MySQL 侧用删除触发器维护派生行，避免孤儿记录。
            cursor.execute("DROP TRIGGER IF EXISTS `trg_follow_ups_delete_cascade`")
            cursor.execute(
                """
CREATE TRIGGER `trg_follow_ups_delete_cascade` BEFORE DELETE ON `follow_ups`
FOR EACH ROW
BEGIN
  DELETE FROM `attachments`
   WHERE `follow_up_id` = OLD.`id`
      OR (`object_type` = 'follow_up' AND `object_id` = OLD.`id`);
END
"""
            )
            cursor.execute("DROP TRIGGER IF EXISTS `trg_deals_delete_cascade`")
            cursor.execute(
                """
CREATE TRIGGER `trg_deals_delete_cascade` BEFORE DELETE ON `deals`
FOR EACH ROW
BEGIN
  DELETE FROM `attachments`
   WHERE `follow_up_id` IN (
           SELECT `id` FROM `follow_ups` WHERE `deal_id` = OLD.`id`
         )
      OR (`object_type` = 'deal' AND `object_id` = OLD.`id`);
  DELETE FROM `follow_ups` WHERE `deal_id` = OLD.`id`;
  DELETE FROM `quote_items`
   WHERE `quote_id` IN (SELECT `id` FROM `deal_quotes` WHERE `deal_id` = OLD.`id`);
  DELETE FROM `deal_quotes` WHERE `deal_id` = OLD.`id`;
  DELETE FROM `deal_items` WHERE `deal_id` = OLD.`id`;
  DELETE FROM `deal_tags` WHERE `deal_id` = OLD.`id`;
END
"""
            )
            cursor.execute("DROP TRIGGER IF EXISTS `trg_quote_items_delete_cascade`")
            cursor.execute(
                """
CREATE TRIGGER `trg_quote_items_delete_cascade` BEFORE DELETE ON `deal_quotes`
FOR EACH ROW
BEGIN
  DELETE FROM `quote_items` WHERE `quote_id` = OLD.`id`;
END
"""
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def mysql_runtime_seed(conn) -> None:
    """播种字典、产品主档和迁移版本；调用方负责 commit。"""
    import json

    from app.dicts import DICT_SEEDS
    from app.migrations import MIGRATION_VERSION
    from app.product_catalog import seed_product_catalog
    from app.security import now_iso

    now = now_iso()
    for dict_code, entries in DICT_SEEDS.items():
        for entry in entries:
            meta = entry.get("meta")
            if isinstance(meta, dict):
                meta = json.dumps(meta, ensure_ascii=False)
            conn.execute(
                "INSERT OR IGNORE INTO dict_items"
                " (dict_code, key, label, sort, enabled, meta, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dict_code,
                    entry["key"],
                    entry["label"],
                    int(entry.get("sort") or 0),
                    1 if entry.get("enabled", True) else 0,
                    meta,
                    now,
                    now,
                ),
            )
    seed_product_catalog(conn)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note)"
        " VALUES (?, ?, ?)",
        (MIGRATION_VERSION, now, "MySQL schema baseline v2_020"),
    )
