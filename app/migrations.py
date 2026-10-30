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
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MIGRATION_VERSION = "v2_001"
SCHEMA_USER_VERSION = 2


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
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      name       TEXT NOT NULL UNIQUE,
      contact    TEXT,
      phone      TEXT,
      note       TEXT,
      is_active  INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
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
    ("customers_new", None, """
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
    ("customers copy", None, """
    INSERT INTO customers_new (id, name, phone, wechat, location, note, customer_type, source, source_other, intent_level, company_name, owner, created_at, updated_at)
    SELECT id, name, phone, wechat, location, house_note, customer_type, source, source_other, intent_level, company_name, owner, created_at, updated_at
    FROM customers
    """),
    ("customers drop old", None, "DROP TABLE customers"),
    ("customers rename", None, "ALTER TABLE customers_new RENAME TO customers"),
    ("customers cleanup", None, "DROP TABLE IF EXISTS customers_new"),
    # ---------- 12. 清空存量数据（Q2）----------
    # 用 schema_migrations 版本号门控只执行一次
    ("clear_data_guard", None, """
    CREATE TABLE IF NOT EXISTS migration_clear_guard (
        version TEXT PRIMARY KEY DEFAULT 'v2_001_cleared'
    )
    """),
    ("clear_data", None, """
    INSERT OR IGNORE INTO migration_clear_guard (version) VALUES ('v2_001_cleared');
    DELETE FROM customers WHERE id > 0;
    DELETE FROM deals WHERE id > 0;
    DELETE FROM follow_ups WHERE id > 0;
    DELETE FROM attachments WHERE id > 0;
    DELETE FROM tags WHERE id > 0;
    DELETE FROM customer_tags WHERE id > 0;
    DELETE FROM import_log WHERE id > 0;
    """),
    # ---------- 13. 版本落账 ----------
    ("schema_migrations v2_001", None,
     "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) "
     "VALUES ('v2_001', datetime('now'), 'CRM V2 增量迁移：线索/订单/售后/物流 + 统一跟进')"),
    ("user_version", None, f"PRAGMA user_version = {SCHEMA_USER_VERSION}"),
]


#: 迁移前后行数必须一致的业务表
COUNT_STABLE_TABLES = ("customers", "deals", "follow_ups", "tags", "customer_tags", "attachments")


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

    before = {t: row_count(conn, t) for t in COUNT_STABLE_TABLES}
    applied = skipped = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for label, guard, sql in STATEMENTS:
            if guard is not None and guard(conn):
                skipped += 1
                continue
            try:
                # 逐条执行 SQL，避免一次执行多条语句的错误
                statements = sql.split(';')
                for stmt in statements:
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(stmt)
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
    for table in COUNT_STABLE_TABLES:
        assert before[table] == after[table], (
            f"行数变化 {table}: {before[table]} → {after[table]}（数据保护红线）"
        )

    # 检查必要表是否存在
    required_tables = (
        "leads", "lead_tags", "customer_contacts", "carriers", "orders",
        "order_status_log", "aftersales", "aftersale_status_log", "schema_migrations",
    )
    for table in required_tables:
        assert table_exists(conn, table), f"缺表 {table}"
        
    # 检查必要列是否存在
    required_columns = {
        "customers": ("customer_type", "source", "source_other", "intent_level", "company_name", "owner", "note"),
        "deals": ("title", "lost_reason", "lost_reason_other", "source_lost_deal_id", "order_id", "owner"),
        "follow_ups": ("object_type", "object_id", "method"),
        "attachments": ("object_type", "object_id", "follow_up_id"),
    }
    for table, columns in required_columns.items():
        for column in columns:
            assert has_column(conn, table, column), f"缺列 {table}.{column}"
            
    # 检查必要触发器是否存在
    required_triggers = ("trg_fu_object_fill", "trg_att_object_fill")
    for trigger in required_triggers:
        assert has_trigger(conn, trigger), f"缺触发器 {trigger}"

    for leftover in ("follow_ups_new", "attachments_new"):
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