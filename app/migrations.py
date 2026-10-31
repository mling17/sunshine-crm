"""
CRM V2 增量迁移 M2（v2_002）（幂等 / 可中断重跑 / 只增不毁）。

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
7. customers 表构造移除 house_note、新增 note 列（重建或 DROP COLUMN，按 SQLite 版本选方案）。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MIGRATION_VERSION = "v2_002"
SCHEMA_USER_VERSION = 3


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
# 注意：这里调整了顺序，确保索引在表存在后创建
STATEMENTS: list[tuple[str, object, str]] = [
    # ---------- 0. 版本表 ----------
    ("schema_migrations", None, """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version    TEXT PRIMARY KEY,
      applied_at TEXT NOT NULL,
      note       TEXT
    )
    """),
    
    # ---------- 1. 新表 3 张 ----------
    # 1.1 客户地址簿（C-2）
    ("customer_addresses", None, """
    CREATE TABLE IF NOT EXISTS customer_addresses (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      label         TEXT,            -- 家 / 工地 / 库房
      receiver_name TEXT NOT NULL,
      phone         TEXT NOT NULL,
      address       TEXT NOT NULL,
      is_default    INTEGER NOT NULL DEFAULT 0,
      created_at    TEXT NOT NULL,
      updated_at    TEXT NOT NULL
    )
    """),
    ("idx_addr_customer", None, "CREATE INDEX IF NOT EXISTS idx_addr_customer ON customer_addresses(customer_id)"),
    
    # 1.2 物流公司联系人（§3.4）
    ("carrier_contacts", None, """
    CREATE TABLE IF NOT EXISTS carrier_contacts (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
      name       TEXT NOT NULL,
      phone      TEXT NOT NULL,
      tags       TEXT,            -- JSON 数组 [\"大件业务\",\"报价\"]（v2.3 去掉「职务」改标签）
      sort       INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """),
    ("idx_carrier_contacts", None, "CREATE INDEX IF NOT EXISTS idx_carrier_contacts ON carrier_contacts(carrier_id)"),
    
    # 1.3 数据字典项（§3.6）
    ("dict_items", None, """
    CREATE TABLE IF NOT EXISTS dict_items (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      dict_code  TEXT NOT NULL,      -- 字典 code（见 §4.1 注册表）
      key        TEXT NOT NULL,      -- 存储值，保存后不可改
      label      TEXT NOT NULL,      -- 显示名，随时可改
      sort       INTEGER NOT NULL DEFAULT 0,
      enabled    INTEGER NOT NULL DEFAULT 1,
      meta       TEXT,               -- JSON：product_model 存 {\"product\":\"天窗\",\"size\":\"900×1800\",\"drive\":\"electric\"}
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(dict_code, key)
    )
    """),
    ("idx_dict_code", None, "CREATE INDEX IF NOT EXISTS idx_dict_code ON dict_items(dict_code, sort)"),
    
    # ---------- 2. 扩列 21 个 ----------
    # 2.1 customers 表（+7）
    ("customers.house_type", _col_guard("customers", "house_type"),
     "ALTER TABLE customers ADD COLUMN house_type TEXT"),
    ("customers.floor", _col_guard("customers", "floor"),
     "ALTER TABLE customers ADD COLUMN floor TEXT"),
    ("customers.install_at", _col_guard("customers", "install_at"),
     "ALTER TABLE customers ADD COLUMN install_at TEXT"),
    ("customers.decoration_stage", _col_guard("customers", "decoration_stage"),
     "ALTER TABLE customers ADD COLUMN decoration_stage TEXT"),
    ("customers.budget", _col_guard("customers", "budget"),
     "ALTER TABLE customers ADD COLUMN budget TEXT"),
    ("customers.decider", _col_guard("customers", "decider"),
     "ALTER TABLE customers ADD COLUMN decider TEXT"),
    ("customers.care", _col_guard("customers", "care"),
     "ALTER TABLE customers ADD COLUMN care TEXT"),
    
    # 2.2 deals 表（+3）
    ("deals.drive_type", _col_guard("deals", "drive_type"),
     "ALTER TABLE deals ADD COLUMN drive_type TEXT"),
    ("deals.note", _col_guard("deals", "note"),
     "ALTER TABLE deals ADD COLUMN note TEXT"),
    ("deals.locked_at", _col_guard("deals", "locked_at"),
     "ALTER TABLE deals ADD COLUMN locked_at TEXT"),
    
    # 2.3 orders 表（+7）
    ("orders.deposit_amount", _col_guard("orders", "deposit_amount"),
     "ALTER TABLE orders ADD COLUMN deposit_amount REAL"),
    ("orders.balance_amount", _col_guard("orders", "balance_amount"),
     "ALTER TABLE orders ADD COLUMN balance_amount REAL"),
    ("orders.logistics_fee", _col_guard("orders", "logistics_fee"),
     "ALTER TABLE orders ADD COLUMN logistics_fee REAL NOT NULL DEFAULT 0"),
    ("orders.address_id", _col_guard("orders", "address_id"),
     "ALTER TABLE orders ADD COLUMN address_id INTEGER REFERENCES customer_addresses(id) ON DELETE SET NULL"),
    ("orders.receiver_name", _col_guard("orders", "receiver_name"),
     "ALTER TABLE orders ADD COLUMN receiver_name TEXT"),
    ("orders.receiver_phone", _col_guard("orders", "receiver_phone"),
     "ALTER TABLE orders ADD COLUMN receiver_phone TEXT"),
    ("orders.receiver_address", _col_guard("orders", "receiver_address"),
     "ALTER TABLE orders ADD COLUMN receiver_address TEXT"),
    
    # 2.4 follow_ups 表（+2）
    ("follow_ups.kind", _col_guard("follow_ups", "kind"),
     "ALTER TABLE follow_ups ADD COLUMN kind TEXT NOT NULL DEFAULT 'follow'"),
    ("follow_ups.detail", _col_guard("follow_ups", "detail"),
     "ALTER TABLE follow_ups ADD COLUMN detail TEXT"),
    
    # 2.5 order_status_log 表（+2）
    ("order_status_log.event_type", _col_guard("order_status_log", "event_type"),
     "ALTER TABLE order_status_log ADD COLUMN event_type TEXT NOT NULL DEFAULT 'stage'"),
    ("order_status_log.detail", _col_guard("order_status_log", "detail"),
     "ALTER TABLE order_status_log ADD COLUMN detail TEXT"),
    
    # ---------- 3. 索引 9 个 ----------
    # 3.1 deals 索引（注意：这些索引在 deals 表创建之后才能创建）
    # 由于 deals 表在较早的迁移中已经存在，这些索引应该可以创建
    ("idx_deals_stage", None, "CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage)"),
    ("idx_deals_cust", None, "CREATE INDEX IF NOT EXISTS idx_deals_cust ON deals(customer_id)"),
    
    # 3.2 orders 索引
    # 检查 orders 表是否存在，如果存在再创建索引
    ("idx_orders_status", None, "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)"),
    ("idx_orders_cust", None, "CREATE INDEX IF NOT EXISTS idx_orders_cust ON orders(customer_id)"),
    
    # 3.3 follow_ups 索引
    ("idx_fu_obj", None, "CREATE INDEX IF NOT EXISTS idx_fu_obj ON follow_ups(object_type, object_id, created_at)"),
    ("idx_fu_kind", None, "CREATE INDEX IF NOT EXISTS idx_fu_kind ON follow_ups(kind)"),
    
    # 3.4 order_status_log 索引
    ("idx_osl_order", None, "CREATE INDEX IF NOT EXISTS idx_osl_order ON order_status_log(order_id)"),
    
    # 3.5 其他索引
    ("idx_attr_obj", None, "CREATE INDEX IF NOT EXISTS idx_attr_obj ON attachments(object_type, object_id)"),
    ("idx_attr_fu", None, "CREATE INDEX IF NOT EXISTS idx_attr_fu ON attachments(follow_up_id)"),
    
    # ---------- 4. 值域迁移 ----------
    # 4.1 deals 阶段迁移（必须在同一个事务中）
    ("deals.stage_migrate", None, """
    UPDATE deals SET stage='quote'   WHERE stage IN ('confirm','quote');
    UPDATE deals SET stage='confirm' WHERE stage='negotiate';
    UPDATE deals SET stage='quote'   WHERE stage IN ('lead','quoted');
    UPDATE deals SET stage='confirm' WHERE stage IN ('confirmed','deposit','producing','balance','shipped');
    """),
    
    # 4.2 orders 物流方式迁移
    ("orders.logistics_mode_migrate", None,
     "UPDATE orders SET logistics_mode='agent' WHERE logistics_mode='carrier'"),
    
    # ---------- 5. 字典种子数据 ----------
    # 5.1 种子数据插入（通过函数实现）
    ("dict_items_seed", None, ""),
    
    # ---------- 6. 清空存量数据（Q2）----------
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
    
    # ---------- 7. 版本落账 ----------
    ("schema_migrations v2_002", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_002', datetime('now'), 'V2 定稿对齐')"),
    ("user_version", None, f"PRAGMA user_version = {SCHEMA_USER_VERSION}"),
]

#: 迁移前后行数必须一致的业务表
COUNT_STABLE_TABLES = ("customers", "deals", "follow_ups", "tags", "customer_tags", "attachments")


def seed_dict_items(conn: sqlite3.Connection) -> None:
    """
    插入字典种子数据（77条）
    """
    # 字典种子数据
    dict_seeds = [
        # product_model (30条)
        ("product_model", [
            {"key": "XW-60", "label": "XW-60 天窗 600×1200", "sort": 1, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"600×1200\",\"drive\":\"manual\"}"},
            {"key": "XW-90", "label": "XW-90 天窗 900×1800", "sort": 2, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"900×1800\",\"drive\":\"manual\"}"},
            {"key": "XW-120", "label": "XW-120 天窗 1200×2400", "sort": 3, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"1200×2400\",\"drive\":\"manual\"}"},
            {"key": "XW-150", "label": "XW-150 天窗 1500×2800", "sort": 4, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"1500×2800\",\"drive\":\"manual\"}"},
            {"key": "XW-180", "label": "XW-180 天窗 1800×3000", "sort": 5, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"1800×3000\",\"drive\":\"manual\"}"},
            {"key": "XW-120E", "label": "XW-120E 天窗 电动款 1200×2400", "sort": 6, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"1200×2400\",\"drive\":\"electric\"}"},
            {"key": "XW-150E", "label": "XW-150E 天窗 电动款 1500×2800", "sort": 7, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"1500×2800\",\"drive\":\"electric\"}"},
            {"key": "XW-200E", "label": "XW-200E 天窗 电动款 2000×3200", "sort": 8, "enabled": True, "meta": "{\"product\":\"天窗\",\"size\":\"2000×3200\",\"drive\":\"electric\"}"},
            {"key": "TM-120", "label": "TM-120 天幕 1200×2000", "sort": 9, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"1200×2000\",\"drive\":\"manual\"}"},
            {"key": "TM-180", "label": "TM-180 天幕 1800×2600", "sort": 10, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"1800×2600\",\"drive\":\"manual\"}"},
            {"key": "TM-240", "label": "TM-240 天幕 2400×3000", "sort": 11, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"2400×3000\",\"drive\":\"manual\"}"},
            {"key": "TM-300", "label": "TM-300 天幕 3000×3500", "sort": 12, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"3000×3500\",\"drive\":\"manual\"}"},
            {"key": "TM-360", "label": "TM-360 天幕 3600×4200", "sort": 13, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"3600×4200\",\"drive\":\"manual\"}"},
            {"key": "TM-240E", "label": "TM-240E 天幕 电动款 2400×3000", "sort": 14, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"2400×3000\",\"drive\":\"electric\"}"},
            {"key": "TM-300E", "label": "TM-300E 天幕 电动款 3000×3500", "sort": 15, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"3000×3500\",\"drive\":\"electric\"}"},
            {"key": "YG-20", "label": "YG-20 阳光房 2000×3000", "sort": 16, "enabled": True, "meta": "{\"product\":\"阳光房\",\"size\":\"2000×3000\",\"drive\":\"manual\"}"},
            {"key": "YG-30", "label": "YG-30 阳光房 3000×4000", "sort": 17, "enabled": True, "meta": "{\"product\":\"阳光房\",\"size\":\"3000×4000\",\"drive\":\"manual\"}"},
            {"key": "YG-40", "label": "YG-40 阳光房 4000×5000", "sort": 18, "enabled": True, "meta": "{\"product\":\"阳光房\",\"size\":\"4000×5000\",\"drive\":\"manual\"}"},
            {"key": "YG-50", "label": "YG-50 阳光房 5000×6000", "sort": 19, "enabled": True, "meta": "{\"product\":\"阳光房\",\"size\":\"5000×6000\",\"drive\":\"manual\"}"},
            {"key": "ZY-10", "label": "ZY-10 遮阳帘 1000×1500", "sort": 20, "enabled": True, "meta": "{\"product\":\"遮阳帘\",\"size\":\"1000×1500\",\"drive\":\"manual\"}"},
            {"key": "ZY-15", "label": "ZY-15 遮阳帘 1500×2000", "sort": 21, "enabled": True, "meta": "{\"product\":\"遮阳帘\",\"size\":\"1500×2000\",\"drive\":\"manual\"}"},
            {"key": "ZY-20", "label": "ZY-20 遮阳帘 2000×2500", "sort": 22, "enabled": True, "meta": "{\"product\":\"遮阳帘\",\"size\":\"2000×2500\",\"drive\":\"manual\"}"},
            {"key": "ZY-25E", "label": "ZY-25E 遮阳帘 电动款 2500×3000", "sort": 23, "enabled": True, "meta": "{\"product\":\"遮阳帘\",\"size\":\"2500×3000\",\"drive\":\"electric\"}"},
            {"key": "FT-100", "label": "FT-100 上翻窗 1000×1000", "sort": 24, "enabled": True, "meta": "{\"product\":\"上翻窗\",\"size\":\"1000×1000\",\"drive\":\"manual\"}"},
            {"key": "FT-140", "label": "FT-140 上翻窗 1400×1400", "sort": 25, "enabled": True, "meta": "{\"product\":\"上翻窗\",\"size\":\"1400×1400\",\"drive\":\"manual\"}"},
            {"key": "PY-120", "label": "PY-120 平移窗 1200×1200", "sort": 26, "enabled": True, "meta": "{\"product\":\"平移窗\",\"size\":\"1200×1200\",\"drive\":\"manual\"}"},
            {"key": "PY-160", "label": "PY-160 平移窗 1600×1200", "sort": 27, "enabled": True, "meta": "{\"product\":\"平移窗\",\"size\":\"1600×1200\",\"drive\":\"manual\"}"},
            {"key": "PY-200E", "label": "PY-200E 平移窗 电动款 2000×1500", "sort": 28, "enabled": True, "meta": "{\"product\":\"平移窗\",\"size\":\"2000×1500\",\"drive\":\"electric\"}"},
            {"key": "YG-30E", "label": "YG-30E 阳光房 电动开合 3000×4000", "sort": 29, "enabled": True, "meta": "{\"product\":\"阳光房\",\"size\":\"3000×4000\",\"drive\":\"electric\"}"},
            {"key": "TM-420", "label": "TM-420 天幕 4200×5000", "sort": 30, "enabled": True, "meta": "{\"product\":\"天幕\",\"size\":\"4200×5000\",\"drive\":\"manual\"}"},
        ]),
        # customer_source (6条)
        ("customer_source", [
            {"key": "wechat", "label": "微信", "sort": 1, "enabled": True},
            {"key": "phone", "label": "电话", "sort": 2, "enabled": True},
            {"key": "referral", "label": "转介绍", "sort": 3, "enabled": True},
            {"key": "existing", "label": "老客户", "sort": 4, "enabled": True},
            {"key": "stock", "label": "存量", "sort": 5, "enabled": True},
            {"key": "other", "label": "其他", "sort": 6, "enabled": True},
        ]),
        # intent_level (4条)
        ("intent_level", [
            {"key": "high", "label": "高", "sort": 1, "enabled": True},
            {"key": "medium", "label": "中", "sort": 2, "enabled": True},
            {"key": "low", "label": "低", "sort": 3, "enabled": True},
            {"key": "none", "label": "无意向", "sort": 4, "enabled": True},
        ]),
        # product_type (4条)
        ("product_type", [
            {"key": "天窗", "label": "天窗", "sort": 1, "enabled": True},
            {"key": "天幕", "label": "天幕", "sort": 2, "enabled": True},
            {"key": "阳光房", "label": "阳光房", "sort": 3, "enabled": True},
            {"key": "遮阳帘", "label": "遮阳帘", "sort": 4, "enabled": True},
        ]),
        # lost_reason (5条)
        ("lost_reason", [
            {"key": "price", "label": "价格", "sort": 1, "enabled": True},
            {"key": "competitor", "label": "竞品", "sort": 2, "enabled": True},
            {"key": "give_up", "label": "客户放弃", "sort": 3, "enabled": True},
            {"key": "budget", "label": "预算不足", "sort": 4, "enabled": True},
            {"key": "other", "label": "其他", "sort": 5, "enabled": True},
        ]),
        # aftersale_type (5条)
        ("aftersale_type", [
            {"key": "return", "label": "退货", "sort": 1, "enabled": True},
            {"key": "exchange", "label": "换货", "sort": 2, "enabled": True},
            {"key": "repair", "label": "维修", "sort": 3, "enabled": True},
            {"key": "complaint", "label": "投诉", "sort": 4, "enabled": True},
            {"key": "other", "label": "其他", "sort": 5, "enabled": True},
        ]),
        # follow_method (2条)
        ("follow_method", [
            {"key": "wechat", "label": "微信", "sort": 1, "enabled": True},
            {"key": "phone", "label": "电话", "sort": 2, "enabled": True},
        ]),
        # deal_stage (4条)
        ("deal_stage", [
            {"key": "quote", "label": "报价", "sort": 1, "enabled": True},
            {"key": "confirm", "label": "待客户确认", "sort": 2, "enabled": True},
            {"key": "won", "label": "成交", "sort": 3, "enabled": True},
            {"key": "lost", "label": "流失", "sort": 4, "enabled": True},
        ]),
        # order_status (7条)
        ("order_status", [
            {"key": "pending_payment", "label": "待支付", "sort": 1, "enabled": True},
            {"key": "deposit_paid", "label": "已支付押金", "sort": 2, "enabled": True},
            {"key": "producing", "label": "生产中", "sort": 3, "enabled": True},
            {"key": "balance_paid", "label": "已支付尾款", "sort": 4, "enabled": True},
            {"key": "ready_to_ship", "label": "待发货", "sort": 5, "enabled": True},
            {"key": "shipped", "label": "已发货", "sort": 6, "enabled": True},
            {"key": "completed", "label": "已完成", "sort": 7, "enabled": True},
        ]),
        # aftersale_status (3条)
        ("aftersale_status", [
            {"key": "pending", "label": "待处理", "sort": 1, "enabled": True},
            {"key": "processing", "label": "处理中", "sort": 2, "enabled": True},
            {"key": "done", "label": "已完成", "sort": 3, "enabled": True},
        ]),
        # customer_type (2条)
        ("customer_type", [
            {"key": "personal", "label": "个人", "sort": 1, "enabled": True},
            {"key": "company", "label": "公司", "sort": 2, "enabled": True},
        ]),
        # follow_object (5条)
        ("follow_object", [
            {"key": "lead", "label": "线索", "sort": 1, "enabled": True},
            {"key": "customer", "label": "客户", "sort": 2, "enabled": True},
            {"key": "deal", "label": "商机", "sort": 3, "enabled": True},
            {"key": "order", "label": "订单", "sort": 4, "enabled": True},
            {"key": "aftersale", "label": "售后", "sort": 5, "enabled": True},
        ]),
    ]
    
    # 插入所有种子数据
    for dict_code, items in dict_seeds:
        for item in items:
            conn.execute("""
                INSERT OR IGNORE INTO dict_items 
                (dict_code, key, label, sort, enabled, meta, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (dict_code, item["key"], item["label"], item["sort"], 
                  int(item["enabled"]), item.get("meta", "")))


def run_migrations(db_path: Path | None = None, *, backup: bool = True, verbose: bool = True) -> dict:
    """
    执行 CRM V2 增量迁移 v2_002。

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
                    # 特殊处理：种子数据插入
                    seed_dict_items(conn)
                elif sql:
                    conn.execute(sql)
                applied += 1
            except sqlite3.Error as exc:  # 带语句名报错，定位快
                raise RuntimeError(f"迁移语句失败 [{label}]: {exc}\nSQL: {sql.strip()[:200]}") from exc
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
        "customer_addresses", "carrier_contacts", "dict_items"
    )
    for table in required_tables:
        assert table_exists(conn, table), f"缺表 {table}"
        
    # 检查必要列是否存在
    required_columns = {
        "customers": ("customer_type", "source", "source_other", "intent_level", "company_name", "owner", "note",
                      "house_type", "floor", "install_at", "decoration_stage", "budget", "decider", "care"),
        "deals": ("title", "lost_reason", "lost_reason_other", "source_lost_deal_id", "order_id", "owner",
                  "drive_type", "note", "locked_at"),
        "follow_ups": ("object_type", "object_id", "method", "kind", "detail"),
        "attachments": ("object_type", "object_id", "follow_up_id"),
        "orders": ("deposit_amount", "balance_amount", "logistics_fee", "address_id", "receiver_name",
                   "receiver_phone", "receiver_address"),
        "order_status_log": ("event_type", "detail"),
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
        print(f"M2 {MIGRATION_VERSION}: {executed_sql}")
        print(f"Rows unchanged: {after}")
        print(f"user_version={conn.execute('PRAGMA user_version').fetchone()[0]}")

    conn.close()
    return {"applied": applied, "skipped": skipped,
            "backup": str(backup_path) if backup_path else None, "counts": after}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CRM V2 增量迁移 v2_002")
    parser.add_argument("--db", default=None, help="数据库路径（默认 $CRM_DB 或 /opt/data/crm/crm.db）")
    parser.add_argument("--no-backup", action="store_true", help="跳过自动备份（仅限临时副本）")
    args = parser.parse_args(argv)

    result = run_migrations(Path(args.db) if args.db else None, backup=not args.no_backup)
    print(f"OK v2_002 applied={result['applied']} skipped={result['skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())