"""建表 DDL（计划 §4 定稿，一字不改地收在这里）。

全部语句都是 ``IF NOT EXISTS``：lifespan 每次启动都会跑一遍，幂等、可重复执行。
"""

from __future__ import annotations

from app.db_standard import ensure_active_lead_phone_unique, ensure_standard_columns
from app.db import DBPath, db_conn

ENSURE_SQL: list[str] = [
    # ---------------- 账号 / 会话 ----------------
    """
    CREATE TABLE IF NOT EXISTS users (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      username      TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,            -- PBKDF2：$pbkdf2$<iters>$<salt_hex>$<hash_hex>
      created_at    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
      token      TEXT PRIMARY KEY,            -- secrets.token_hex(32)
      username   TEXT NOT NULL,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL                -- created_at + 12h（固定，不滑动 → 每天重登）
    )
    """,
    # ---------------- 客户 ----------------
    """
    CREATE TABLE IF NOT EXISTS customers (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT NOT NULL,
      phone       TEXT,                       -- 隐私字段：公网必须登录后可见
      wechat      TEXT,
      location    TEXT,                       -- 地区
      house_note  TEXT,
      created_at  TEXT NOT NULL,
      updated_at  TEXT NOT NULL
    )
    """,
    # ---------------- 商机（1 客户 N 商机）----------------
    """
    CREATE TABLE IF NOT EXISTS deals (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      product_type TEXT,                      -- 天窗 / 天幕
      model        TEXT,
      spec         TEXT,                      -- 洞口/跨度等尺寸
      amount       REAL NOT NULL DEFAULT 0,   -- 报价金额
      deposit      REAL NOT NULL DEFAULT 0,   -- 定金（先装后付/定金场景）
      balance      REAL NOT NULL DEFAULT 0,   -- 尾款
      stage        TEXT NOT NULL DEFAULT 'lead',
      closed_at    TEXT,                      -- 进入 won 时置 now()，驱动“本月成交”
      created_at   TEXT NOT NULL,
      updated_at   TEXT NOT NULL
    )
    """,
    # ---------------- 跟进记录 ----------------
    """
    CREATE TABLE IF NOT EXISTS follow_ups (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      deal_id     INTEGER REFERENCES deals(id) ON DELETE CASCADE,  -- 可空=只挂客户
      content     TEXT NOT NULL,
      next_date   TEXT,                       -- 'YYYY-MM-DD'，可空；≤今天 即进待办
      created_at  TEXT NOT NULL
    )
    """,
    # ---------------- 照片（应用层限 3 张）----------------
    """
    CREATE TABLE IF NOT EXISTS attachments (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      follow_up_id  INTEGER NOT NULL REFERENCES follow_ups(id) ON DELETE CASCADE,
      storage_key   TEXT NOT NULL,            -- YYYY/MM/DD/<uuid>.<ext>（相对 CRM_UPLOADS 根）
      file_name     TEXT,
      mime_type     TEXT,
      size          INTEGER NOT NULL DEFAULT 0,
      created_at    TEXT NOT NULL
    )
    """,
    # ---------------- CSV 导入审计 ----------------
    """
    CREATE TABLE IF NOT EXISTS import_log (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      source_name    TEXT NOT NULL,
      column_mapping TEXT,                    -- JSON：Excel 列名 → 系统字段
      row_count      INTEGER NOT NULL DEFAULT 0,
      created_at     TEXT NOT NULL
    )
    """,
    # ---------------- 客户标签（多对多）----------------
    """
    CREATE TABLE IF NOT EXISTS tags (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT NOT NULL UNIQUE,       -- 如：重点客户 / 老客户 / 转介绍 / 微信来的 / 别墅项目
      created_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_tags (
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
      UNIQUE(customer_id, tag_id)
    )
    """,
    # ---------------- 索引 ----------------
    "CREATE INDEX IF NOT EXISTS idx_customers_name  ON customers(name)",
    "CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)",
    "CREATE INDEX IF NOT EXISTS idx_deals_customer  ON deals(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_deals_stage     ON deals(stage)",
    "CREATE INDEX IF NOT EXISTS idx_deals_closed    ON deals(closed_at)",
    "CREATE INDEX IF NOT EXISTS idx_fu_customer     ON follow_ups(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_fu_next_date    ON follow_ups(next_date)",
    "CREATE INDEX IF NOT EXISTS idx_att_fu          ON attachments(follow_up_id)",
    "CREATE INDEX IF NOT EXISTS idx_cust_tag_c      ON customer_tags(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_cust_tag_t      ON customer_tags(tag_id)",
]


def ensure_schema(db_path: DBPath = None) -> None:
    """建库 + 建表 + 建索引（幂等）。lifespan 里调用一次。"""
    with db_conn(db_path) as conn:
        for statement in ENSURE_SQL:
            conn.execute(statement)
        ensure_standard_columns(conn)
        ensure_active_lead_phone_unique(conn)
