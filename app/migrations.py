"""
CRM V2 增量迁移 M1（幂等 / 可中断重跑 / 只增不毁）。

用法（二选一）::

    PYTHONPATH=/opt/data/crm /usr/bin/python3 -m app.migrations [--db PATH] [--no-backup]
    PYTHONPATH=/opt/data/crm /usr/bin/python3 app/migrations.py --db /tmp/copy.db

设计红线：
1. 增量优先：``ALTER TABLE ADD COLUMN`` / ``CREATE TABLE`` / ``CREATE TRIGGER`` 为主。
2. 只重建两张必须放宽 NOT NULL 的表（``follow_ups`` 的 customer_id、``attachments`` 的
   follow_up_id）：**先按行复制 → 比对行数 → 才 DROP**，任何不一致直接抛错退出。
3. 重建走 SQLite 官方 12 步：``PRAGMA foreign_keys=OFF`` → 事务内建新表/复制/删旧/改名 →
   提交后 ``PRAGMA foreign_key_check`` 必须为空 → 再打开外键。迁移期间关外键是为了避免
   DROP 父表时把子表行按 CASCADE 误删。
4. 每条语句带状态 guard：中断后重跑从中间态收敛；已完成的语句跳过。
5. 迁移前后比对业务表行数，任何不一致直接抛错。
6. 清空存量数据：迁移末尾一次性清空业务数据（customers/deals/follow_ups/attachments/tags/customer_tags/import_log），
   保留 users，sessions 可清；用 schema_migrations 版本号门控只执行一次。
7. customers 表构造移除 house_note、新增 note 列（重建或 DROP COLUMN，按 SQLite 版本选方案）
"""

from __future__ import annotations

import argparse
import os
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app.db_standard import ensure_active_lead_phone_unique, ensure_standard_columns

MIGRATION_VERSION = "v2_014"
SCHEMA_USER_VERSION = 14


def default_db_path() -> Path:
    return Path(os.environ.get("CRM_DB") or "/opt/data/crm/crm.db")


# ---------------------------------------------------------------- 小工具
def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone() is not None


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not table_exists(conn, table):
        return False
    return column in [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def has_trigger(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name = ?", (name,)
    ).fetchone() is not None


def row_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _customers_migrated(conn: sqlite3.Connection) -> bool:
    """customers 表已完成 house_note→note 重建则跳过（幂等）。"""
    return has_column(conn, "customers", "note") and not has_column(conn, "customers", "house_note")


def _clear_done(conn: sqlite3.Connection) -> bool:
    """Q2 存量清空已执行过则跳过（幂等，中断重跑安全）。"""
    if not table_exists(conn, "migration_clear_guard"):
        return False
    return conn.execute(
        "SELECT 1 FROM migration_clear_guard WHERE version = 'v2_001_cleared'"
    ).fetchone() is not None


def backup_db(db_path: Path) -> Path:
    """在线一致性备份（sqlite3 备份 API，不受并发写影响）。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = db_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"crm-pre-v2-{stamp}.db"
    src = sqlite3.connect(str(db_path), timeout=15)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


# ---------------------------------------------------------------- guards
def _col_guard(table: str, column: str):
    """列已存在 → 跳过；表不存在（全新库，下面 ensure_schema 才建）→ 跳过。"""

    def guard(conn: sqlite3.Connection) -> bool:
        return (not table_exists(conn, table)) or has_column(conn, table, column)

    return guard


def _once(version: str, *tables: str):
    """一次性数据迁移 guard：表缺失 → 跳过；该版本已落账 → 跳过（绝不重复改写数据）。"""

    def guard(conn: sqlite3.Connection) -> bool:
        if any(not table_exists(conn, t) for t in tables):
            return True
        if not table_exists(conn, "schema_migrations"):
            return False
        return (
            conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone()
            is not None
        )

    return guard


def _tbl_guard(*tables: str):
    """任一表不存在 → 跳过（全新库上索引/UPDATE 不会炸）。"""

    def guard(conn: sqlite3.Connection) -> bool:
        return any(not table_exists(conn, t) for t in tables)

    return guard


def _rebuild_guards(src: str, dst: str, final_ok):
    """三件套 guard：建新表 / 复制行 / 删旧表+改名，全部状态可重入。"""

    def g_create(conn: sqlite3.Connection) -> bool:
        return final_ok(conn) or not table_exists(conn, src)

    def g_copy(conn: sqlite3.Connection) -> bool:
        if g_create(conn):
            return True
        if not table_exists(conn, dst):
            return True
        return row_count(conn, dst) >= row_count(conn, src)

    def g_drop(conn: sqlite3.Connection) -> bool:
        if final_ok(conn) or not table_exists(conn, src):
            return True
        if not table_exists(conn, dst):
            raise RuntimeError(f"{dst} 不存在，禁止 DROP {src}（数据保护）")
        old_n, new_n = row_count(conn, src), row_count(conn, dst)
        if old_n != new_n:
            raise RuntimeError(f"{src} 行数不一致（旧 {old_n} / 新 {new_n}），禁止 DROP（数据保护）")
        return False

    def g_rename(conn: sqlite3.Connection) -> bool:
        if final_ok(conn):
            return True
        return not (table_exists(conn, dst) and not table_exists(conn, src))

    def g_cleanup(conn: sqlite3.Connection) -> bool:
        # 终态已就绪且残留空表 → 删（收敛中断态）
        if table_exists(conn, dst) and row_count(conn, dst) == 0 and final_ok(conn):
            return False
        return True

    return g_create, g_copy, g_drop, g_rename, g_cleanup


fu_final = lambda conn: has_column(conn, "follow_ups", "object_type")
att_final = lambda conn: has_column(conn, "attachments", "object_type")

G_FU_CREATE, G_FU_COPY, G_FU_DROP, G_FU_RENAME, G_FU_CLEAN = _rebuild_guards(
    "follow_ups", "follow_ups_new", fu_final)
G_ATT_CREATE, G_ATT_COPY, G_ATT_DROP, G_ATT_RENAME, G_ATT_CLEAN = _rebuild_guards(
    "attachments", "attachments_new", att_final)


# ---------------------------------------------------------------- 语句
# (label, guard, sql)；guard 返回 True = 跳过
STATEMENTS: list[tuple[str, object, str]] = [
    # ---------- 0. 版本表 ----------
    ("schema_migrations", None, """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version    TEXT PRIMARY KEY,
      applied_at TEXT NOT NULL,
      note       TEXT
    )
    """),
    # ---------- 1. 线索 ----------
    ("leads", None, """
    CREATE TABLE IF NOT EXISTS leads (
      id                    INTEGER PRIMARY KEY AUTOINCREMENT,
      name                  TEXT,
      phone                 TEXT,
      wechat                TEXT,
      lead_type             TEXT NOT NULL DEFAULT 'personal',
      company_name          TEXT,
      source                TEXT,
      source_other          TEXT,
      location              TEXT,
      note                  TEXT,
      intent_level          TEXT,
      status                TEXT NOT NULL DEFAULT 'new',
      invalid_reason        TEXT,
      invalid_reason_other  TEXT,
      converted_customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
      converted_deal_id     INTEGER REFERENCES deals(id)     ON DELETE SET NULL,
      owner                 TEXT,
      created_at            TEXT NOT NULL,
      updated_at            TEXT NOT NULL
    )
    """),
    ("idx_leads_status", None, "CREATE INDEX IF NOT EXISTS idx_leads_status  ON leads(status)"),
    ("idx_leads_phone", None, "CREATE INDEX IF NOT EXISTS idx_leads_phone   ON leads(phone)"),
    ("idx_leads_wechat", None, "CREATE INDEX IF NOT EXISTS idx_leads_wechat  ON leads(wechat)"),
    ("idx_leads_created", None, "CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at)"),
    ("lead_tags", None, """
    CREATE TABLE IF NOT EXISTS lead_tags (
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
      UNIQUE(lead_id, tag_id)
    )
    """),
    ("idx_lead_tags_lead", None, "CREATE INDEX IF NOT EXISTS idx_lead_tags_lead ON lead_tags(lead_id)"),
    # ---------- 2. 客户扩展 + 多联系人 ----------
    ("customers.customer_type", _col_guard("customers", "customer_type"),
     "ALTER TABLE customers ADD COLUMN customer_type TEXT NOT NULL DEFAULT 'personal'"),
    ("customers.source", _col_guard("customers", "source"),
     "ALTER TABLE customers ADD COLUMN source TEXT"),
    ("customers.source_other", _col_guard("customers", "source_other"),
     "ALTER TABLE customers ADD COLUMN source_other TEXT"),
    ("customers.intent_level", _col_guard("customers", "intent_level"),
     "ALTER TABLE customers ADD COLUMN intent_level TEXT"),
    ("customers.company_name", _col_guard("customers", "company_name"),
     "ALTER TABLE customers ADD COLUMN company_name TEXT"),
    ("customers.owner", _col_guard("customers", "owner"),
     "ALTER TABLE customers ADD COLUMN owner TEXT"),
    ("customer_contacts", None, """
    CREATE TABLE IF NOT EXISTS customer_contacts (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      name        TEXT NOT NULL,
      phone       TEXT,
      wechat      TEXT,
      is_primary  INTEGER NOT NULL DEFAULT 0,
      created_at  TEXT NOT NULL,
      updated_at  TEXT NOT NULL
    )
    """),
    ("idx_cc_customer", None, "CREATE INDEX IF NOT EXISTS idx_cc_customer ON customer_contacts(customer_id)"),
    # ---------- 3. 商机扩展 ----------
    ("deals.title", _col_guard("deals", "title"), "ALTER TABLE deals ADD COLUMN title TEXT"),
    ("deals.lost_reason", _col_guard("deals", "lost_reason"), "ALTER TABLE deals ADD COLUMN lost_reason TEXT"),
    ("deals.lost_reason_other", _col_guard("deals", "lost_reason_other"),
     "ALTER TABLE deals ADD COLUMN lost_reason_other TEXT"),
    ("deals.source_lost_deal_id", _col_guard("deals", "source_lost_deal_id"),
     "ALTER TABLE deals ADD COLUMN source_lost_deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL"),
    ("deals.order_id", _col_guard("deals", "order_id"), "ALTER TABLE deals ADD COLUMN order_id INTEGER"),
    ("deals.owner", _col_guard("deals", "owner"), "ALTER TABLE deals ADD COLUMN owner TEXT"),
    ("idx_deals_order", None, "CREATE INDEX IF NOT EXISTS idx_deals_order ON deals(order_id)"),
    # ---------- 4. 物流公司主数据（先建，orders 外键指向它）----------
    ("carriers", None, """
    CREATE TABLE IF NOT EXISTS carriers (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      name           TEXT NOT NULL UNIQUE,
      code           TEXT,
      contact_person TEXT,
      phone          TEXT,
      address        TEXT,
      is_active      INTEGER NOT NULL DEFAULT 1,
      created_at     TEXT NOT NULL,
      updated_at     TEXT NOT NULL
    )
    """),
    ("idx_carriers_active", None, "CREATE INDEX IF NOT EXISTS idx_carriers_active ON carriers(is_active)"),
    # ---------- 5. 订单 + 状态日志 ----------
    ("orders", None, """
    CREATE TABLE IF NOT EXISTS orders (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      order_no       TEXT NOT NULL UNIQUE,
      customer_id    INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      deal_id        INTEGER NOT NULL UNIQUE REFERENCES deals(id) ON DELETE RESTRICT,
      product_type   TEXT,
      model          TEXT,
      spec           TEXT,
      amount         REAL NOT NULL DEFAULT 0,
      deposit_paid   REAL NOT NULL DEFAULT 0,
      balance_paid   REAL NOT NULL DEFAULT 0,
      logistics_mode TEXT,
      carrier_id     INTEGER REFERENCES carriers(id) ON DELETE RESTRICT,
      tracking_no    TEXT,
      shipped_at     TEXT,
      completed_at   TEXT,
      status         TEXT NOT NULL DEFAULT 'pending_payment',
      note           TEXT,
      owner          TEXT,
      created_at     TEXT NOT NULL,
      updated_at     TEXT NOT NULL
    )
    """),
    ("idx_orders_status", None, "CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status)"),
    ("idx_orders_customer", None, "CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)"),
    ("idx_orders_created", None, "CREATE INDEX IF NOT EXISTS idx_orders_created  ON orders(created_at)"),
    ("order_status_log", None, """
    CREATE TABLE IF NOT EXISTS order_status_log (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id       INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
      from_status    TEXT,
      to_status      TEXT NOT NULL,
      deposit_paid   REAL,
      balance_paid   REAL,
      screenshot_ids TEXT,
      logistics_mode TEXT,
      carrier_id     INTEGER REFERENCES carriers(id) ON DELETE SET NULL,
      tracking_no    TEXT,
      note           TEXT,
      created_at     TEXT NOT NULL
    )
    """),
    ("idx_osl_order", None, "CREATE INDEX IF NOT EXISTS idx_osl_order ON order_status_log(order_id)"),
    # ---------- 6. 售后 + 状态日志 ----------
    ("aftersales", None, """
    CREATE TABLE IF NOT EXISTS aftersales (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      no            TEXT NOT NULL UNIQUE,
      order_id      INTEGER NOT NULL REFERENCES orders(id)    ON DELETE RESTRICT,
      customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      type          TEXT NOT NULL,
      type_other    TEXT,
      description   TEXT NOT NULL,
      status        TEXT NOT NULL DEFAULT 'pending',
      result        TEXT,
      reject_reason TEXT,
      closed_at     TEXT,
      created_at    TEXT NOT NULL,
      updated_at    TEXT NOT NULL
    )
    """),
    ("idx_as_status", None, "CREATE INDEX IF NOT EXISTS idx_as_status   ON aftersales(status)"),
    ("idx_as_order", None, "CREATE INDEX IF NOT EXISTS idx_as_order    ON aftersales(order_id)"),
    ("idx_as_customer", None, "CREATE INDEX IF NOT EXISTS idx_as_customer ON aftersales(customer_id)"),
    ("idx_as_created", None, "CREATE INDEX IF NOT EXISTS idx_as_created  ON aftersales(created_at)"),
    ("aftersale_status_log", None, """
    CREATE TABLE IF NOT EXISTS aftersale_status_log (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      aftersale_id INTEGER NOT NULL REFERENCES aftersales(id) ON DELETE CASCADE,
      from_status  TEXT,
      to_status    TEXT NOT NULL,
      note         TEXT,
      created_at   TEXT NOT NULL
    )
    """),
    ("idx_asl_aftersale", None, "CREATE INDEX IF NOT EXISTS idx_asl_aftersale ON aftersale_status_log(aftersale_id)"),
    # ---------- 7. follow_ups 重建：放宽 customer_id（线索期无客户）----------
    ("follow_ups_new", G_FU_CREATE, """
    CREATE TABLE IF NOT EXISTS follow_ups_new (
      id          INTEGER PRIMARY KEY,
      object_type TEXT NOT NULL DEFAULT 'customer',
      object_id   INTEGER,
      customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
      deal_id     INTEGER REFERENCES deals(id)     ON DELETE CASCADE,
      method      TEXT,
      content     TEXT NOT NULL,
      next_date   TEXT,
      created_at  TEXT NOT NULL
    )
    """),
    ("follow_ups copy", G_FU_COPY, """
    INSERT OR IGNORE INTO follow_ups_new
      (id, object_type, object_id, customer_id, deal_id, method, content, next_date, created_at)
    SELECT id,
           CASE WHEN deal_id IS NOT NULL THEN 'deal' ELSE 'customer' END,
           COALESCE(deal_id, customer_id),
           customer_id, deal_id, NULL, content, next_date, created_at
      FROM follow_ups
    """),
    ("follow_ups drop old", G_FU_DROP, "DROP TABLE follow_ups"),
    ("follow_ups rename", G_FU_RENAME, "ALTER TABLE follow_ups_new RENAME TO follow_ups"),
    ("follow_ups cleanup", G_FU_CLEAN, "DROP TABLE IF EXISTS follow_ups_new"),
    # ---------- 8. attachments 重建：放宽 follow_up_id（订单截图不挂跟进）----------
    ("attachments_new", G_ATT_CREATE, """
    CREATE TABLE IF NOT EXISTS attachments_new (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      object_type  TEXT NOT NULL DEFAULT 'follow_up',
      object_id    INTEGER,
      follow_up_id INTEGER REFERENCES follow_ups(id) ON DELETE CASCADE,
      storage_key  TEXT NOT NULL,
      file_name    TEXT,
      mime_type    TEXT,
      size         INTEGER NOT NULL DEFAULT 0,
      created_at   TEXT NOT NULL
    )
    """),
    ("attachments copy", G_ATT_COPY, """
    INSERT OR IGNORE INTO attachments_new
      (id, object_type, object_id, follow_up_id, storage_key, file_name, mime_type, size, created_at)
    SELECT id, 'follow_up', follow_up_id, follow_up_id, storage_key, file_name, mime_type, size, created_at
      FROM attachments
    """),
    ("attachments drop old", G_ATT_DROP, "DROP TABLE attachments"),
    ("attachments rename", G_ATT_RENAME, "ALTER TABLE attachments_new RENAME TO attachments"),
    ("attachments cleanup", G_ATT_CLEAN, "DROP TABLE IF EXISTS attachments_new"),
    # ---------- 9. 索引 / 触发器（重建后原索引已随表消失，必须重建）----------
    ("idx_fu_object", None, "CREATE INDEX IF NOT EXISTS idx_fu_object   ON follow_ups(object_type, object_id)"),
    ("idx_fu_customer", None, "CREATE INDEX IF NOT EXISTS idx_fu_customer ON follow_ups(customer_id)"),
    ("idx_fu_deal", None, "CREATE INDEX IF NOT EXISTS idx_fu_deal     ON follow_ups(deal_id)"),
    ("idx_fu_next_date", None, "CREATE INDEX IF NOT EXISTS idx_fu_next_date ON follow_ups(next_date)"),
    ("idx_att_obj", None, "CREATE INDEX IF NOT EXISTS idx_att_obj ON attachments(object_type, object_id)"),
    ("idx_att_fu", None, "CREATE INDEX IF NOT EXISTS idx_att_fu  ON attachments(follow_up_id)"),
    ("trg_fu_object_fill", None, """
    CREATE TRIGGER IF NOT EXISTS trg_fu_object_fill
    AFTER INSERT ON follow_ups
    WHEN NEW.object_id IS NULL
    BEGIN
      UPDATE follow_ups
         SET object_type = CASE WHEN NEW.deal_id IS NOT NULL THEN 'deal' ELSE 'customer' END,
             object_id   = COALESCE(NEW.deal_id, NEW.customer_id)
       WHERE id = NEW.id;
    END
    """),
    ("trg_att_object_fill", None, """
    CREATE TRIGGER IF NOT EXISTS trg_att_object_fill
    AFTER INSERT ON attachments
    WHEN NEW.object_id IS NULL AND NEW.follow_up_id IS NOT NULL
    BEGIN
      UPDATE attachments
         SET object_type = 'follow_up', object_id = NEW.follow_up_id
       WHERE id = NEW.id;
    END
    """),
    # ---------- 10. 存量数据口径 ----------
    ("follow_ups backfill", None, """
    UPDATE follow_ups
       SET object_type = CASE WHEN deal_id IS NOT NULL THEN 'deal' ELSE 'customer' END,
           object_id   = COALESCE(deal_id, customer_id)
     WHERE object_id IS NULL
    """),
    ("deals stage map", None, """
    UPDATE deals SET stage = CASE stage
        WHEN 'lead'      THEN 'confirm'
        WHEN 'quoted'    THEN 'quote'
        WHEN 'confirmed' THEN 'negotiate'
        WHEN 'deposit'   THEN 'negotiate'
        WHEN 'producing' THEN 'negotiate'
        WHEN 'balance'   THEN 'negotiate'
        WHEN 'shipped'   THEN 'negotiate'
        ELSE stage END
     WHERE stage NOT IN ('confirm','quote','negotiate','won','lost')
    """),
    ("customers source stock", None,
     "UPDATE customers SET source = 'stock' WHERE source IS NULL OR TRIM(source) = ''"),
    ("customers type personal", None,
     "UPDATE customers SET customer_type = 'personal' "
     "WHERE customer_type IS NULL OR TRIM(customer_type) = ''"),
    # ---------- 11. customers 表结构变更：移除 house_note，增加 note 列 ----------
    # 注意：这里我们采用重建方式，因为需要移除 house_note 列
    ("customers_new", _customers_migrated, """
    CREATE TABLE IF NOT EXISTS customers_new (
      id               INTEGER PRIMARY KEY AUTOINCREMENT,
      name             TEXT NOT NULL,
      phone            TEXT,
      wechat           TEXT,
      location         TEXT,
      note             TEXT,
      customer_type    TEXT NOT NULL DEFAULT 'personal',
      source           TEXT,
      source_other     TEXT,
      intent_level     TEXT,
      company_name     TEXT,
      owner            TEXT,
      created_at       TEXT NOT NULL,
      updated_at       TEXT NOT NULL
    )
    """),
    ("customers copy", _customers_migrated, """
    INSERT OR REPLACE INTO customers_new (id, name, phone, wechat, location, note, customer_type, source, source_other, intent_level, company_name, owner, created_at, updated_at)
    SELECT id, name, phone, wechat, location, house_note, customer_type, source, source_other, intent_level, company_name, owner, created_at, updated_at
    FROM customers
    """),
    ("customers drop old", _customers_migrated, "DROP TABLE customers"),
    ("customers rename", _customers_migrated, "ALTER TABLE customers_new RENAME TO customers"),
    ("customers cleanup", _customers_migrated, "DROP TABLE IF EXISTS customers_new"),
    # ---------- 12. 清空存量数据（Q2）----------
    # 用 schema_migrations 版本号门控只执行一次
    ("clear_data_guard", None, """
    CREATE TABLE IF NOT EXISTS migration_clear_guard (
        version TEXT PRIMARY KEY DEFAULT 'v2_001_cleared'
    )
    """),
    # Q2：存量清空（逐表、单条语句、_clear_done 幂等；中断重跑安全）
    *[
        (f"clear_{_t}", _clear_done, f"DELETE FROM {_t}")
        for _t in ("customers", "deals", "follow_ups", "attachments",
                   "tags", "customer_tags", "import_log")
    ],
    ("clear_data_mark", None,
     "INSERT OR IGNORE INTO migration_clear_guard (version) VALUES ('v2_001_cleared')"),
    # ---------- 13. 版本落账 ----------
    ("schema_migrations v2_001", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_001', datetime('now'), 'CRM V2 增量迁移：线索/订单/售后/物流 + 统一跟进')"),
    ("user_version", None, f"PRAGMA user_version = {SCHEMA_USER_VERSION}"),

    # ================= v2_002：CRM V2 定稿对齐（PLANNER-V3 §3）=================
    # ---------- 14. 新表 3 张 ----------
    ("customer_addresses", None, """
    CREATE TABLE IF NOT EXISTS customer_addresses (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      label         TEXT,
      receiver_name TEXT NOT NULL,
      phone         TEXT NOT NULL,
      address       TEXT NOT NULL,
      is_default    INTEGER NOT NULL DEFAULT 0,
      created_at    TEXT NOT NULL,
      updated_at    TEXT NOT NULL
    )
    """),
    ("carrier_contacts", None, """
    CREATE TABLE IF NOT EXISTS carrier_contacts (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
      name       TEXT NOT NULL,
      phone      TEXT NOT NULL,
      tags       TEXT,
      sort       INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """),
    ("dict_items", None, """
    CREATE TABLE IF NOT EXISTS dict_items (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      dict_code  TEXT NOT NULL,
      key        TEXT NOT NULL,
      label      TEXT NOT NULL,
      sort       INTEGER NOT NULL DEFAULT 0,
      enabled    INTEGER NOT NULL DEFAULT 1,
      meta       TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(dict_code, key)
    )
    """),

    # ---------- 15. 扩列 21 个 ----------
    # 15.1 customers 画像 +7
    ("customers.house_type",       _col_guard("customers", "house_type"),       "ALTER TABLE customers ADD COLUMN house_type TEXT"),
    ("customers.floor",            _col_guard("customers", "floor"),            "ALTER TABLE customers ADD COLUMN floor TEXT"),
    ("customers.install_at",       _col_guard("customers", "install_at"),       "ALTER TABLE customers ADD COLUMN install_at TEXT"),
    ("customers.decoration_stage", _col_guard("customers", "decoration_stage"), "ALTER TABLE customers ADD COLUMN decoration_stage TEXT"),
    ("customers.budget",           _col_guard("customers", "budget"),           "ALTER TABLE customers ADD COLUMN budget TEXT"),
    ("customers.decider",          _col_guard("customers", "decider"),          "ALTER TABLE customers ADD COLUMN decider TEXT"),
    ("customers.care",             _col_guard("customers", "care"),             "ALTER TABLE customers ADD COLUMN care TEXT"),
    # 15.2 deals +3
    ("deals.drive_type", _col_guard("deals", "drive_type"), "ALTER TABLE deals ADD COLUMN drive_type TEXT"),
    ("deals.note",       _col_guard("deals", "note"),       "ALTER TABLE deals ADD COLUMN note TEXT"),
    ("deals.locked_at",  _col_guard("deals", "locked_at"),  "ALTER TABLE deals ADD COLUMN locked_at TEXT"),
    # 15.3 orders +7
    ("orders.deposit_amount",   _col_guard("orders", "deposit_amount"),   "ALTER TABLE orders ADD COLUMN deposit_amount REAL"),
    ("orders.balance_amount",   _col_guard("orders", "balance_amount"),   "ALTER TABLE orders ADD COLUMN balance_amount REAL"),
    ("orders.logistics_fee",    _col_guard("orders", "logistics_fee"),    "ALTER TABLE orders ADD COLUMN logistics_fee REAL NOT NULL DEFAULT 0"),
    ("orders.address_id",       _col_guard("orders", "address_id"),       "ALTER TABLE orders ADD COLUMN address_id INTEGER REFERENCES customer_addresses(id) ON DELETE SET NULL"),
    ("orders.receiver_name",    _col_guard("orders", "receiver_name"),    "ALTER TABLE orders ADD COLUMN receiver_name TEXT"),
    ("orders.receiver_phone",   _col_guard("orders", "receiver_phone"),   "ALTER TABLE orders ADD COLUMN receiver_phone TEXT"),
    ("orders.receiver_address", _col_guard("orders", "receiver_address"), "ALTER TABLE orders ADD COLUMN receiver_address TEXT"),
    # 15.4 follow_ups +2（统一跟进扩为对象履历）
    ("follow_ups.kind",   _col_guard("follow_ups", "kind"),   "ALTER TABLE follow_ups ADD COLUMN kind TEXT NOT NULL DEFAULT 'follow'"),
    ("follow_ups.detail", _col_guard("follow_ups", "detail"), "ALTER TABLE follow_ups ADD COLUMN detail TEXT"),
    # 15.5 order_status_log +2（状态日志扩为事件流）
    ("order_status_log.event_type", _col_guard("order_status_log", "event_type"), "ALTER TABLE order_status_log ADD COLUMN event_type TEXT NOT NULL DEFAULT 'stage'"),
    ("order_status_log.detail",     _col_guard("order_status_log", "detail"),     "ALTER TABLE order_status_log ADD COLUMN detail TEXT"),

    # ---------- 16. 新增索引 6 个（表不存在则跳过；同列的旧索引 schema.py 已有，不重复建）----------
    ("idx_addr_customer",    _tbl_guard("customer_addresses"), "CREATE INDEX IF NOT EXISTS idx_addr_customer ON customer_addresses(customer_id)"),
    ("idx_carrier_contacts", _tbl_guard("carrier_contacts"),   "CREATE INDEX IF NOT EXISTS idx_carrier_contacts ON carrier_contacts(carrier_id)"),
    ("idx_dict_code",        _tbl_guard("dict_items"),         "CREATE INDEX IF NOT EXISTS idx_dict_code ON dict_items(dict_code, sort)"),
    ("idx_deals_stage",      _tbl_guard("deals"),              "CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage)"),
    ("idx_orders_status",    _tbl_guard("orders"),             "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)"),
    ("idx_fu_kind",          _tbl_guard("follow_ups"),         "CREATE INDEX IF NOT EXISTS idx_fu_kind ON follow_ups(kind)"),

    # ---------- 17. 值域迁移（单条语句，顺序不可反）----------
    # 旧 confirm=需求确认 → 新第一段 quote；旧 negotiate → 新第二段 confirm
    ("deals.stage_confirm_to_quote", _once("v2_002", "deals"),
     "UPDATE deals SET stage='quote' WHERE stage IN ('confirm','quote')"),
    ("deals.stage_negotiate_to_confirm", _once("v2_002", "deals"),
     "UPDATE deals SET stage='confirm' WHERE stage='negotiate'"),
    ("deals.stage_v1_to_quote", _once("v2_002", "deals"),
     "UPDATE deals SET stage='quote' WHERE stage IN ('lead','quoted')"),
    ("deals.stage_v1_to_confirm", _once("v2_002", "deals"),
     "UPDATE deals SET stage='confirm' WHERE stage IN ('confirmed','deposit','producing','balance','shipped')"),
    ("orders.logistics_mode_migrate", _once("v2_002", "orders"),
     "UPDATE orders SET logistics_mode='agent' WHERE logistics_mode='carrier'"),

    # ---------- 18. 字典种子（幂等，只补缺，不覆盖用户改过的 label）----------
    ("dict_items_seed", None, ""),

    # ---------- 19. v2_002 落账 ----------
    ("schema_migrations v2_002", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_002', datetime('now'), 'CRM V2 定稿对齐：地址簿/物流联系人/数据字典 + 21 列')"),
    ("user_version v2_002", None, f"PRAGMA user_version = {SCHEMA_USER_VERSION}"),
    # ---------- 20. v2_003：用户显示名（右上角下拉「修改个人信息」用）----------
    ("users.display_name", _col_guard("users", "display_name"),
     "ALTER TABLE users ADD COLUMN display_name TEXT"),
    ("schema_migrations v2_003", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_003', datetime('now'), '用户显示名 display_name')"),
    # ---------- 21. v2_004：已有跟进的线索回填「跟进中」 ----------
    ("leads.following_backfill", _once("v2_004", "leads", "follow_ups"),
     "UPDATE leads SET status = 'following' "
     "WHERE status = 'new' AND EXISTS ("
     " SELECT 1 FROM follow_ups f"
     " WHERE f.object_type = 'lead' AND f.object_id = leads.id AND f.kind = 'follow'"
     ")"),
    ("schema_migrations v2_004", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_004', datetime('now'), '线索有跟进后进入跟进中')"),
    ("user_version v2_004", None, "PRAGMA user_version = 4"),
    # ---------- 22. v2_005：全局 create_time/update_time/is_delete + 线索电话唯一 ----------
    ("standardize_audit_columns", None, ""),
    ("schema_migrations v2_005", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_005', datetime('now'), '统一审计时间与软删除字段；线索电话唯一')"),
    ("user_version v2_005", None, "PRAGMA user_version = 5"),
    # ---------- 23. v2_006：公司线索主联系人回填 ----------
    ("customer_company_primary_contact_backfill",
     _once("v2_006", "leads", "customers", "customer_contacts"), """
    INSERT INTO customer_contacts
        (customer_id, name, phone, wechat, is_primary, created_at, updated_at)
    SELECT l.converted_customer_id, TRIM(l.name), l.phone, l.wechat, 1,
           l.created_at, COALESCE(NULLIF(l.updated_at, ''), l.created_at)
    FROM leads l
    INNER JOIN customers c
        ON c.id = l.converted_customer_id AND c.is_delete = 0
    WHERE l.is_delete = 0
      AND l.status = 'converted'
      AND l.lead_type = 'company'
      AND l.converted_customer_id IS NOT NULL
      AND NULLIF(TRIM(l.name), '') IS NOT NULL
      AND l.id = (
          SELECT l2.id
          FROM leads l2
          WHERE l2.is_delete = 0
            AND l2.status = 'converted'
            AND l2.lead_type = 'company'
            AND l2.converted_customer_id = l.converted_customer_id
            AND NULLIF(TRIM(l2.name), '') IS NOT NULL
          ORDER BY COALESCE(NULLIF(l2.updated_at, ''), l2.created_at) DESC, l2.id DESC
          LIMIT 1
      )
      AND NOT EXISTS (
          SELECT 1 FROM customer_contacts cc
          WHERE cc.customer_id = l.converted_customer_id AND cc.is_delete = 0
      )
    """),
    ("schema_migrations v2_006", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_006', datetime('now'), '公司客户主联系人继承与客户搜索口径')"),
    ("user_version v2_006", None, "PRAGMA user_version = 6"),
    # ---------- 24. v2_007：尺寸/洞口尺寸分隔符统一为 * ----------
    ("normalize_deal_spec_separator",
     _once("v2_007", "deals", "orders"), """
    UPDATE deals
    SET spec = replace(replace(replace(spec, 'x', '*'), 'X', '*'), '×', '*')
    WHERE spec IS NOT NULL
      AND (instr(spec, 'x') > 0 OR instr(spec, 'X') > 0 OR instr(spec, '×') > 0)
    """),
    ("normalize_order_spec_separator",
     _once("v2_007", "deals", "orders"), """
    UPDATE orders
    SET spec = replace(replace(replace(spec, 'x', '*'), 'X', '*'), '×', '*')
    WHERE spec IS NOT NULL
      AND (instr(spec, 'x') > 0 OR instr(spec, 'X') > 0 OR instr(spec, '×') > 0)
    """),
    ("schema_migrations v2_007", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_007', datetime('now'), '尺寸/洞口尺寸分隔符统一为星号')"),
    # ---------- 25. v2_008：产品主档 + 商机/订单产品快照 ----------
    ("products", None, """
    CREATE TABLE IF NOT EXISTS products (
      id                    INTEGER PRIMARY KEY AUTOINCREMENT,
      seed_key              TEXT NOT NULL UNIQUE,
      code                  TEXT NOT NULL,
      name                  TEXT NOT NULL,
      category              TEXT NOT NULL DEFAULT '天窗',
      series                TEXT,
      structure             TEXT,
      opening_mode          TEXT,
      drive_type            TEXT,
      frame_type            TEXT,
      leaf_type             TEXT,
      edge_type             TEXT,
      leaf_count            INTEGER,
      min_width             REAL,
      max_width             REAL,
      min_height            REAL,
      max_height            REAL,
      attributes            TEXT,
      source_template       TEXT,
      form_storage_key      TEXT,
      form_file_name        TEXT,
      form_file_size        INTEGER NOT NULL DEFAULT 0,
      form_sha256           TEXT,
      form_uploaded_at      TEXT,
      description           TEXT,
      is_active             INTEGER NOT NULL DEFAULT 1,
      created_at            TEXT NOT NULL,
      updated_at            TEXT NOT NULL,
      create_time           TEXT NOT NULL DEFAULT '',
      update_time           TEXT NOT NULL DEFAULT '',
      is_delete             INTEGER NOT NULL DEFAULT 0
    )
    """),
    ("idx_products_category", _tbl_guard("products"),
     "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category, series)"),
    ("idx_products_active", _tbl_guard("products"),
     "CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active, is_delete)"),
    ("uq_products_code_active", _tbl_guard("products"),
     "CREATE UNIQUE INDEX IF NOT EXISTS uq_products_code_active"
     " ON products(code) WHERE is_delete = 0"),
    ("deals.product_id", _col_guard("deals", "product_id"),
     "ALTER TABLE deals ADD COLUMN product_id INTEGER"),
    ("deals.product_code_snapshot", _col_guard("deals", "product_code_snapshot"),
     "ALTER TABLE deals ADD COLUMN product_code_snapshot TEXT"),
    ("deals.product_name_snapshot", _col_guard("deals", "product_name_snapshot"),
     "ALTER TABLE deals ADD COLUMN product_name_snapshot TEXT"),
    ("deals.product_config_snapshot", _col_guard("deals", "product_config_snapshot"),
     "ALTER TABLE deals ADD COLUMN product_config_snapshot TEXT"),
    ("orders.product_id", _col_guard("orders", "product_id"),
     "ALTER TABLE orders ADD COLUMN product_id INTEGER"),
    ("orders.product_code_snapshot", _col_guard("orders", "product_code_snapshot"),
     "ALTER TABLE orders ADD COLUMN product_code_snapshot TEXT"),
    ("orders.product_name_snapshot", _col_guard("orders", "product_name_snapshot"),
     "ALTER TABLE orders ADD COLUMN product_name_snapshot TEXT"),
    ("orders.product_config_snapshot", _col_guard("orders", "product_config_snapshot"),
     "ALTER TABLE orders ADD COLUMN product_config_snapshot TEXT"),
    ("idx_deals_product", _tbl_guard("deals"),
     "CREATE INDEX IF NOT EXISTS idx_deals_product ON deals(product_id)"),
    ("idx_orders_product", _tbl_guard("orders"),
     "CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_id)"),
    # v2_009 columns precede the seed so old v2_008 catalogs gain their Excel immediately.
    ("products.form_storage_key", _col_guard("products", "form_storage_key"),
     "ALTER TABLE products ADD COLUMN form_storage_key TEXT"),
    ("products.form_file_name", _col_guard("products", "form_file_name"),
     "ALTER TABLE products ADD COLUMN form_file_name TEXT"),
    ("products.form_file_size", _col_guard("products", "form_file_size"),
     "ALTER TABLE products ADD COLUMN form_file_size INTEGER NOT NULL DEFAULT 0"),
    ("products.form_sha256", _col_guard("products", "form_sha256"),
     "ALTER TABLE products ADD COLUMN form_sha256 TEXT"),
    ("products.form_uploaded_at", _col_guard("products", "form_uploaded_at"),
     "ALTER TABLE products ADD COLUMN form_uploaded_at TEXT"),
    ("product_catalog_seed", None, ""),
    ("standardize_product_audit_columns", None, ""),
    ("schema_migrations v2_008", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_008', datetime('now'), '产品主档：123 个下单表模板 + 商机/订单产品快照')"),
    ("schema_migrations v2_009", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_009', datetime('now'), '每个产品必须包含一份对应 Excel 下单表')"),
    # ---------- 26. v2_010：多产品商机/订单、整单优惠、客户确认 ----------
    ("deal_items", None, """
    CREATE TABLE IF NOT EXISTS deal_items (
      id                       INTEGER PRIMARY KEY AUTOINCREMENT,
      deal_id                  INTEGER NOT NULL,
      product_id               INTEGER,
      product_code_snapshot    TEXT,
      product_name_snapshot    TEXT,
      product_config_snapshot  TEXT,
      product_type             TEXT,
      model                    TEXT,
      drive_type               TEXT,
      quantity                 INTEGER NOT NULL DEFAULT 1,
      spec                     TEXT,
      production_spec          TEXT,
      unit_price               REAL NOT NULL DEFAULT 0,
      amount                   REAL NOT NULL DEFAULT 0,
      note                     TEXT,
      sort                     INTEGER NOT NULL DEFAULT 0,
      created_at               TEXT NOT NULL,
      updated_at               TEXT NOT NULL,
      create_time              TEXT NOT NULL DEFAULT '',
      update_time              TEXT NOT NULL DEFAULT '',
      is_delete                INTEGER NOT NULL DEFAULT 0
    )
    """),
    ("order_items", None, """
    CREATE TABLE IF NOT EXISTS order_items (
      id                       INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id                 INTEGER NOT NULL,
      source_deal_item_id      INTEGER,
      product_id               INTEGER,
      product_code_snapshot    TEXT,
      product_name_snapshot    TEXT,
      product_config_snapshot  TEXT,
      product_type             TEXT,
      model                    TEXT,
      drive_type               TEXT,
      quantity                 INTEGER NOT NULL DEFAULT 1,
      spec                     TEXT,
      production_spec          TEXT,
      unit_price               REAL NOT NULL DEFAULT 0,
      amount                   REAL NOT NULL DEFAULT 0,
      note                     TEXT,
      sort                     INTEGER NOT NULL DEFAULT 0,
      created_at               TEXT NOT NULL,
      updated_at               TEXT NOT NULL,
      create_time              TEXT NOT NULL DEFAULT '',
      update_time              TEXT NOT NULL DEFAULT '',
      is_delete                INTEGER NOT NULL DEFAULT 0
    )
    """),
    ("idx_deal_items_deal", _tbl_guard("deal_items"),
     "CREATE INDEX IF NOT EXISTS idx_deal_items_deal ON deal_items(deal_id, is_delete, sort)"),
    ("idx_order_items_order", _tbl_guard("order_items"),
     "CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id, is_delete, sort)"),
    ("orders.product_total", _col_guard("orders", "product_total"),
     "ALTER TABLE orders ADD COLUMN product_total REAL NOT NULL DEFAULT 0"),
    ("orders.discount_amount", _col_guard("orders", "discount_amount"),
     "ALTER TABLE orders ADD COLUMN discount_amount REAL NOT NULL DEFAULT 0"),
    ("orders.discount_reason", _col_guard("orders", "discount_reason"),
     "ALTER TABLE orders ADD COLUMN discount_reason TEXT"),
    ("orders.product_payable", _col_guard("orders", "product_payable"),
     "ALTER TABLE orders ADD COLUMN product_payable REAL NOT NULL DEFAULT 0"),
    ("orders.customer_confirmed_at", _col_guard("orders", "customer_confirmed_at"),
     "ALTER TABLE orders ADD COLUMN customer_confirmed_at TEXT"),
    ("orders.customer_confirmation_note", _col_guard("orders", "customer_confirmation_note"),
     "ALTER TABLE orders ADD COLUMN customer_confirmation_note TEXT"),
    ("deal_items_legacy_backfill", _once("v2_010", "deals", "deal_items"), """
    INSERT INTO deal_items (
      deal_id, product_id, product_code_snapshot, product_name_snapshot,
      product_config_snapshot, product_type, model, drive_type, quantity,
      spec, production_spec, unit_price, amount, note, sort,
      created_at, updated_at, create_time, update_time, is_delete
    )
    SELECT d.id, d.product_id, d.product_code_snapshot, d.product_name_snapshot,
      d.product_config_snapshot, d.product_type, d.model, d.drive_type, 1,
      d.spec, NULL, COALESCE(d.amount, 0), COALESCE(d.amount, 0), d.note, 0,
      d.created_at, d.updated_at, '', '', 0
    FROM deals d
    WHERE COALESCE(d.is_delete, 0) = 0
      AND NOT EXISTS (
        SELECT 1 FROM deal_items i
        WHERE i.deal_id = d.id AND COALESCE(i.is_delete, 0) = 0
      )
    """),
    ("order_items_legacy_backfill", _once("v2_010", "orders", "order_items"), """
    INSERT INTO order_items (
      order_id, source_deal_item_id, product_id, product_code_snapshot,
      product_name_snapshot, product_config_snapshot, product_type, model,
      drive_type, quantity, spec, production_spec, unit_price, amount, note,
      sort, created_at, updated_at, create_time, update_time, is_delete
    )
    SELECT o.id, NULL, o.product_id, o.product_code_snapshot,
      o.product_name_snapshot, o.product_config_snapshot, o.product_type,
      o.model, d.drive_type, 1, o.spec, NULL,
      COALESCE(o.amount, 0), COALESCE(o.amount, 0), o.note, 0,
      o.created_at, o.updated_at, '', '', 0
    FROM orders o
    LEFT JOIN deals d ON d.id = o.deal_id
    WHERE COALESCE(o.is_delete, 0) = 0
      AND NOT EXISTS (
        SELECT 1 FROM order_items i
        WHERE i.order_id = o.id AND COALESCE(i.is_delete, 0) = 0
      )
    """),
    ("orders.amount_breakdown_backfill", _once("v2_010", "orders"), """
    UPDATE orders
    SET product_total = COALESCE(amount, 0),
        discount_amount = 0,
        product_payable = COALESCE(amount, 0)
    WHERE COALESCE(product_total, 0) = 0 AND COALESCE(amount, 0) > 0
    """),
    ("schema_migrations v2_010", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_010', datetime('now'), '多产品明细、整单优惠、独立运费与客户确认')"),
    # ---------- 27. v2_011：商机内报价单 + 下单表快照 + 履历关联 ----------
    ("deal_quotes", None, """
    CREATE TABLE IF NOT EXISTS deal_quotes (
      id                    INTEGER PRIMARY KEY AUTOINCREMENT,
      quote_no              TEXT NOT NULL UNIQUE,
      deal_id               INTEGER NOT NULL,
      customer_id           INTEGER NOT NULL,
      title                 TEXT NOT NULL,
      note                  TEXT,
      status                TEXT NOT NULL DEFAULT 'draft',
      amount                REAL NOT NULL DEFAULT 0,
      confirmed_at          TEXT,
      confirmation_note     TEXT,
      order_id              INTEGER,
      created_at            TEXT NOT NULL,
      updated_at            TEXT NOT NULL,
      create_time           TEXT NOT NULL DEFAULT '',
      update_time           TEXT NOT NULL DEFAULT '',
      is_delete             INTEGER NOT NULL DEFAULT 0
    )
    """),
    ("quote_items", None, """
    CREATE TABLE IF NOT EXISTS quote_items (
      id                       INTEGER PRIMARY KEY AUTOINCREMENT,
      quote_id                 INTEGER NOT NULL,
      deal_id                  INTEGER NOT NULL,
      product_id               INTEGER NOT NULL,
      product_code_snapshot    TEXT,
      product_name_snapshot    TEXT,
      product_config_snapshot  TEXT,
      product_type             TEXT,
      model                    TEXT,
      drive_type               TEXT,
      quantity                 INTEGER NOT NULL DEFAULT 1,
      spec                     TEXT,
      production_spec          TEXT,
      unit_price               REAL NOT NULL DEFAULT 0,
      amount                   REAL NOT NULL DEFAULT 0,
      note                     TEXT,
      form_storage_key         TEXT,
      form_file_name           TEXT,
      form_file_size           INTEGER NOT NULL DEFAULT 0,
      form_mime_type           TEXT,
      form_sha256              TEXT,
      form_content_json        TEXT,
      sort                     INTEGER NOT NULL DEFAULT 0,
      created_at               TEXT NOT NULL,
      updated_at               TEXT NOT NULL,
      create_time              TEXT NOT NULL DEFAULT '',
      update_time              TEXT NOT NULL DEFAULT '',
      is_delete                INTEGER NOT NULL DEFAULT 0
    )
    """),
    ("idx_deal_quotes_deal", _tbl_guard("deal_quotes"),
     "CREATE INDEX IF NOT EXISTS idx_deal_quotes_deal ON deal_quotes(deal_id, is_delete, id)"),
    ("uq_deal_quotes_confirmed", _tbl_guard("deal_quotes"),
     "CREATE UNIQUE INDEX IF NOT EXISTS uq_deal_quotes_confirmed"
     " ON deal_quotes(deal_id) WHERE status = 'confirmed' AND is_delete = 0"),
    ("idx_quote_items_quote", _tbl_guard("quote_items"),
     "CREATE INDEX IF NOT EXISTS idx_quote_items_quote ON quote_items(quote_id, is_delete, sort)"),
    ("orders.quote_id", _col_guard("orders", "quote_id"),
     "ALTER TABLE orders ADD COLUMN quote_id INTEGER"),
    ("order_items.source_quote_item_id", _col_guard("order_items", "source_quote_item_id"),
     "ALTER TABLE order_items ADD COLUMN source_quote_item_id INTEGER"),
    ("follow_ups.quote_id", _col_guard("follow_ups", "quote_id"),
     "ALTER TABLE follow_ups ADD COLUMN quote_id INTEGER"),
    ("idx_orders_quote", _tbl_guard("orders"),
     "CREATE INDEX IF NOT EXISTS idx_orders_quote ON orders(quote_id)"),
    ("idx_fu_quote", _tbl_guard("follow_ups"),
     "CREATE INDEX IF NOT EXISTS idx_fu_quote ON follow_ups(quote_id)"),
    ("schema_migrations v2_011", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_011', datetime('now'), '商机报价单、Excel下单表、履历关联与订单来源')"),
    # ---------- 28. v2_012：下单表保存前识别、A1 校验与预览图片 ----------
    ("quote_items.recognized_total", _col_guard("quote_items", "recognized_total"),
     "ALTER TABLE quote_items ADD COLUMN recognized_total REAL NOT NULL DEFAULT 0"),
    ("quote_items.a1_value", _col_guard("quote_items", "a1_value"),
     "ALTER TABLE quote_items ADD COLUMN a1_value TEXT"),
    ("quote_items.amount_cell", _col_guard("quote_items", "amount_cell"),
     "ALTER TABLE quote_items ADD COLUMN amount_cell TEXT"),
    ("quote_items.form_preview_storage_key", _col_guard("quote_items", "form_preview_storage_key"),
     "ALTER TABLE quote_items ADD COLUMN form_preview_storage_key TEXT"),
    ("quote_items.recognized_total_backfill", _once("v2_012", "quote_items"),
     "UPDATE quote_items SET recognized_total = amount WHERE recognized_total = 0 AND amount > 0"),
    ("schema_migrations v2_012", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_012', datetime('now'), '下单表Sheet1识别、A1产品校验、合计金额和预览图片')"),
    # ---------- 29. v2_013：报价单状态与商机展示口径 ----------
    ("dict_deal_stage_won_label_v2_013", None,
     "UPDATE dict_items SET label = '客户已确认', updated_at = datetime('now')"
     " WHERE dict_code = 'deal_stage' AND key = 'won' AND label = '成交'"),
    ("dict_deal_stage_lost_label_v2_013", None,
     "UPDATE dict_items SET label = '作废', updated_at = datetime('now')"
     " WHERE dict_code = 'deal_stage' AND key = 'lost' AND label IN ('流失', '作废')"),
    ("deals.quote_stage_priority_v2_013",
     _once("v2_013", "deals", "deal_quotes"), """
    UPDATE deals
    SET stage = CASE
          WHEN EXISTS (SELECT 1 FROM deal_quotes q WHERE q.deal_id = deals.id
                       AND q.is_delete = 0 AND q.status = 'confirmed') THEN 'won'
          WHEN EXISTS (SELECT 1 FROM deal_quotes q WHERE q.deal_id = deals.id
                       AND q.is_delete = 0 AND q.status = 'pending') THEN 'confirm'
          WHEN EXISTS (SELECT 1 FROM deal_quotes q WHERE q.deal_id = deals.id
                       AND q.is_delete = 0 AND q.status = 'draft') THEN 'quote'
          WHEN EXISTS (SELECT 1 FROM deal_quotes q WHERE q.deal_id = deals.id
                       AND q.is_delete = 0) THEN 'lost'
          ELSE stage END,
        amount = COALESCE((
          SELECT q.amount FROM deal_quotes q WHERE q.deal_id = deals.id
          AND q.is_delete = 0 AND q.status = 'confirmed'
          ORDER BY q.id DESC LIMIT 1
        ), 0),
        closed_at = (
          SELECT q.confirmed_at FROM deal_quotes q WHERE q.deal_id = deals.id
          AND q.is_delete = 0 AND q.status = 'confirmed'
          ORDER BY q.id DESC LIMIT 1
        )
    WHERE EXISTS (SELECT 1 FROM deal_quotes q WHERE q.deal_id = deals.id
                  AND q.is_delete = 0)
    """),
    ("schema_migrations v2_013", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_013', datetime('now'), '报价单报价/待确认/客户已确认/作废状态与管理动作')"),
    ("user_version v2_013", None, f"PRAGMA user_version = {SCHEMA_USER_VERSION}"),
    # ---------- 30. v2_014：商机自动标签/手动标签 ----------
    ("deal_tags", None, """
    CREATE TABLE IF NOT EXISTS deal_tags (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      deal_id     INTEGER NOT NULL,
      tag_id      INTEGER NOT NULL,
      source      TEXT NOT NULL DEFAULT 'manual',
      created_at  TEXT NOT NULL,
      updated_at  TEXT NOT NULL,
      create_time TEXT NOT NULL DEFAULT '',
      update_time TEXT NOT NULL DEFAULT '',
      is_delete   INTEGER NOT NULL DEFAULT 0,
      UNIQUE(deal_id, tag_id, source)
    )
    """),
    ("idx_deal_tags_deal", _tbl_guard("deal_tags"),
     "CREATE INDEX IF NOT EXISTS idx_deal_tags_deal ON deal_tags(deal_id, is_delete)"),
    ("idx_deal_tags_tag", _tbl_guard("deal_tags"),
     "CREATE INDEX IF NOT EXISTS idx_deal_tags_tag ON deal_tags(tag_id)"),
    ("schema_migrations v2_014", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_014', datetime('now'), '商机手动标签与报价待确认/金额自动标签')"),
    ("user_version v2_014", None, f"PRAGMA user_version = {SCHEMA_USER_VERSION}"),
]


#: 迁移前后行数必须一致的业务表
COUNT_STABLE_TABLES = ("customers", "deals", "follow_ups", "tags", "customer_tags", "attachments")


def seed_dict_items(conn: sqlite3.Connection) -> None:
    """字典种子落库（幂等）。

    数据唯一定义在 `app/dicts.py::DICT_SEEDS` —— 这里**不复制一份**，
    否则中文改名后两边必然漂移（PLANNER-V3 §4.2 单一真源）。
    `INSERT OR IGNORE`：只补缺，不覆盖用户已经改过的 label / sort / enabled。
    """
    from app.dicts import DICT_SEEDS

    for dict_code, entries in DICT_SEEDS.items():
        for entry in entries:
            meta = entry.get("meta")
            if isinstance(meta, dict):
                meta = json.dumps(meta, ensure_ascii=False)
            conn.execute(
                "INSERT OR IGNORE INTO dict_items"
                " (dict_code, key, label, sort, enabled, meta, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (
                    dict_code,
                    entry["key"],
                    entry["label"],
                    int(entry.get("sort") or 0),
                    1 if entry.get("enabled", True) else 0,
                    meta,
                ),
            )


def run_migrations(db_path: Path | None = None, *, backup: bool = True, verbose: bool = True) -> dict:
    """
    执行 CRM V2 增量迁移。
    
    Args:
        db_path: 数据库路径
        backup: 是否自动备份
        verbose: 是否打印详细信息
        
    Returns:
        迁移结果字典
    """
    db_path = Path(db_path) if db_path else default_db_path()
    if not db_path.exists():
        raise SystemExit(f"库不存在：{db_path}")

    backup_path = None
    if backup:
        backup_path = backup_db(db_path)

    conn = sqlite3.connect(str(db_path), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # 官方 12 步：重建期间必须关外键，否则 DROP 父表会按 CASCADE 误删子表行
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA busy_timeout=10000")

    cleared_before = _clear_done(conn)
    before = {t: row_count(conn, t) for t in COUNT_STABLE_TABLES}
    applied = skipped = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for label, guard, sql in STATEMENTS:
            if guard is not None and guard(conn):
                skipped += 1
                continue
            try:
                if label == "dict_items_seed":
                    seed_dict_items(conn)
                elif label == "product_catalog_seed":
                    from app.product_catalog import seed_product_catalog

                    seed_product_catalog(conn)
                elif label == "standardize_audit_columns":
                    ensure_standard_columns(conn)
                    ensure_active_lead_phone_unique(conn)
                elif label == "standardize_product_audit_columns":
                    ensure_standard_columns(conn)
                else:
                    conn.execute(sql)
            except sqlite3.Error as exc:  # 带语句名报错，定位快
                raise RuntimeError(f"迁移语句失败 [{label}]: {exc}\nSQL: {sql.strip()[:200]}") from exc
            applied += 1
        conn.execute("COMMIT")
        executed_sql = f"{applied} executed / {skipped} skipped"
    except BaseException:
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()
        raise

    conn.execute("PRAGMA foreign_keys=ON")

    # ---------- 验收 ----------
    after = {t: row_count(conn, t) for t in COUNT_STABLE_TABLES}
    if not cleared_before and _clear_done(conn):
        # Q2（用户拍板）：本次迁移执行了存量清空，行数保护不适用；断言清空结果
        for table in COUNT_STABLE_TABLES:
            assert after[table] == 0, f"Q2 清空后 {table} 应为空，实际 {after[table]} 行"
    else:
        for table in COUNT_STABLE_TABLES:
            assert before[table] == after[table], (
                f"行数变化 {table}: {before[table]} → {after[table]}（数据保护红线）"
            )

    # 检查必要表是否存在
    required_tables = (
        "leads", "lead_tags", "customer_contacts", "carriers", "orders",
        "order_status_log", "aftersales", "aftersale_status_log", "schema_migrations",
        "products", "deal_items", "order_items", "deal_quotes", "quote_items",
    )
    for table in required_tables:
        assert table_exists(conn, table), f"缺表 {table}"
        
    # 检查必要列是否存在
    required_columns = {
        "customers": ("customer_type", "source", "source_other", "intent_level", "company_name", "owner", "note"),
        "deals": (
            "title", "lost_reason", "lost_reason_other", "source_lost_deal_id",
            "order_id", "owner", "product_id", "product_code_snapshot",
            "product_name_snapshot", "product_config_snapshot",
        ),
        "orders": (
            "product_id", "product_code_snapshot", "product_name_snapshot",
            "product_config_snapshot", "product_total", "discount_amount",
            "product_payable", "customer_confirmed_at", "quote_id",
        ),
        "follow_ups": ("object_type", "object_id", "method", "quote_id"),
        "attachments": ("object_type", "object_id", "follow_up_id"),
        "quote_items": (
            "recognized_total", "a1_value", "amount_cell", "form_preview_storage_key",
        ),
        "products": (
            "form_storage_key", "form_file_name", "form_file_size",
            "form_sha256", "form_uploaded_at",
        ),
    }
    for table, columns in required_columns.items():
        for column in columns:
            assert has_column(conn, table, column), f"缺列 {table}.{column}"
            
    # 检查必要触发器是否存在
    required_triggers = ("trg_fu_object_fill", "trg_att_object_fill")
    for trigger in required_triggers:
        assert has_trigger(conn, trigger), f"缺触发器 {trigger}"

    for leftover in ("follow_ups_new", "attachments_new", "customers_new"):
        if table_exists(conn, leftover) and row_count(conn, leftover) == 0:
            conn.execute(f"DROP TABLE {leftover}")
    assert not table_exists(conn, "follow_ups_new") and not table_exists(conn, "attachments_new"), \
        "重建残留表未清理"

    orphans = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert not orphans, f"外键孤儿行：{[dict(r) for r in orphans]}"

    version = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,)
    ).fetchone()
    assert version is not None, "版本未落账"

    if verbose:
        print(f"Backup: {backup_path}" if backup_path else "Backup: skipped")
        print(f"M1 {MIGRATION_VERSION}: {executed_sql}")
        print(f"Rows unchanged: {after}")
        print(f"user_version={conn.execute('PRAGMA user_version').fetchone()[0]}")

    conn.close()
    return {"applied": applied, "skipped": skipped,
            "backup": str(backup_path) if backup_path else None, "counts": after}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CRM V2 增量迁移 v2_001")
    parser.add_argument("--db", default=None, help="数据库路径（默认 $CRM_DB 或 /opt/data/crm/crm.db）")
    parser.add_argument("--no-backup", action="store_true", help="跳过自动备份（仅限临时副本）")
    args = parser.parse_args(argv)

    result = run_migrations(Path(args.db) if args.db else None, backup=not args.no_backup)
    print(f"OK v2_001 applied={result['applied']} skipped={result['skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
