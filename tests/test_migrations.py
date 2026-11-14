"""迁移测试（Planner §5.3 / Q2 清空口径）。

本模块**不碰共享测试库**（/tmp/crm-t.db 由 ApiTestCase 使用），
每个用例在独立临时库上建 V1 结构 → 迁移 → 断言。
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.migrations import run_migrations
from app.schema import ensure_schema


def _seed_v1(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    now = "2026-10-30T10:00:00Z"
    conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES ('chen', 'x', ?)", (now,))
    conn.execute("INSERT INTO customers (name, phone, created_at, updated_at) VALUES ('张伟','13800000001',?,?)", (now, now))
    conn.execute("INSERT INTO customers (name, phone, created_at, updated_at) VALUES ('李娜','13900000002',?,?)", (now, now))
    conn.execute("INSERT INTO deals (customer_id, amount, stage, created_at, updated_at) VALUES (1, 8800, 'lead', ?, ?)", (now, now))
    conn.execute("INSERT INTO follow_ups (customer_id, content, created_at) VALUES (1, '首次量尺', ?)", (now,))
    conn.execute("INSERT INTO follow_ups (customer_id, content, created_at) VALUES (2, '微信沟通', ?)", (now,))
    conn.execute("INSERT INTO tags (name, created_at) VALUES ('重点客户', ?)", (now,))
    conn.commit()
    conn.close()


def _rows(db: Path, table: str) -> int:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


class TestMigrations(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "mig.db"
        ensure_schema(self.db)
        _seed_v1(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def test_migration_runs(self):
        result = run_migrations(self.db, backup=False, verbose=False)
        self.assertIn("applied", result)
        conn = sqlite3.connect(str(self.db))
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(customers)")]
        finally:
            conn.close()
        self.assertIn("note", cols)
        self.assertNotIn("house_note", cols)

    def test_migration_idempotent(self):
        r1 = run_migrations(self.db, backup=False, verbose=False)
        r2 = run_migrations(self.db, backup=False, verbose=False)
        self.assertGreaterEqual(r2["skipped"], r1["skipped"])
        self.assertEqual(_rows(self.db, "users"), 1)

    def test_migration_structure(self):
        run_migrations(self.db, backup=False, verbose=False)
        expected = {
            "leads", "lead_tags", "carriers", "orders",
            "order_status_log", "aftersales", "aftersale_status_log", "schema_migrations",
            "customers", "deals", "follow_ups", "attachments", "products",
            "deal_tags", "follow_up_phrases",
        }
        conn = sqlite3.connect(str(self.db))
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        finally:
            conn.close()
        self.assertTrue(expected <= tables, f"缺表：{expected - tables}")
        self.assertNotIn("customer_contacts", tables)
        self.assertIn("trg_fu_object_fill", triggers)

    def test_order_carrier_contact_columns_exist(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(orders)")
            }
        finally:
            conn.close()
        self.assertTrue(
            {
                "carrier_contact_id",
                "carrier_contact_name",
                "carrier_contact_phone",
                "order_name",
            }
            <= columns
        )

    def test_v2_020_backfills_order_name_from_quote_title(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        now = "2026-11-09T10:00:00Z"
        try:
            customer_id = int(conn.execute(
                "INSERT INTO customers (name, created_at, updated_at)"
                " VALUES ('订单名称客户', ?, ?)",
                (now, now),
            ).lastrowid)
            deal_id = int(conn.execute(
                "INSERT INTO deals (customer_id, stage, amount, created_at, updated_at)"
                " VALUES (?, 'confirmed', 8800, ?, ?)",
                (customer_id, now, now),
            ).lastrowid)
            quote_id = int(conn.execute(
                "INSERT INTO deal_quotes"
                " (quote_no, deal_id, customer_id, title, status, amount, created_at, updated_at)"
                " VALUES ('QT-TEST-001', ?, ?, '阳光房报价方案', 'confirmed', 8800, ?, ?)",
                (deal_id, customer_id, now, now),
            ).lastrowid)
            conn.execute(
                "INSERT INTO orders"
                " (order_no, customer_id, deal_id, quote_id, amount, status, created_at, updated_at)"
                " VALUES ('SO-TEST-001', ?, ?, ?, 8800, 'pending_payment', ?, ?)",
                (customer_id, deal_id, quote_id, now, now),
            )
            conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_020'")
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            order_name = conn.execute(
                "SELECT order_name FROM orders WHERE order_no = 'SO-TEST-001'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(order_name, "阳光房报价方案")

    def test_v2_021_archives_other_quotes_after_confirmation(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        now = "2026-11-09T10:00:00Z"
        try:
            customer_id = int(conn.execute(
                "INSERT INTO customers (name, created_at, updated_at)"
                " VALUES ('报价归档客户', ?, ?)",
                (now, now),
            ).lastrowid)
            deal_id = int(conn.execute(
                "INSERT INTO deals (customer_id, stage, amount, created_at, updated_at)"
                " VALUES (?, 'won', 8800, ?, ?)",
                (customer_id, now, now),
            ).lastrowid)
            quote_ids = []
            for quote_no, status in (
                ("QT-TEST-CONFIRMED", "confirmed"),
                ("QT-TEST-PENDING", "pending"),
                ("QT-TEST-DRAFT", "draft"),
            ):
                quote_ids.append(int(conn.execute(
                    "INSERT INTO deal_quotes"
                    " (quote_no, deal_id, customer_id, title, status, amount,"
                    " created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, 8800, ?, ?)",
                    (quote_no, deal_id, customer_id, quote_no, status, now, now),
                ).lastrowid))
            conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_021'")
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            statuses = [
                row[0] for row in conn.execute(
                    "SELECT status FROM deal_quotes WHERE id IN (?, ?, ?) ORDER BY id",
                    tuple(quote_ids),
                )
            ]
        finally:
            conn.close()
        self.assertEqual(statuses, ["confirmed", "void", "void"])

    def test_v2_022_completes_shipped_orders_and_removes_status(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        now = "2026-11-09T10:00:00Z"
        try:
            customer_id = int(conn.execute(
                "INSERT INTO customers (name, created_at, updated_at)"
                " VALUES ('发货状态迁移客户', ?, ?)",
                (now, now),
            ).lastrowid)
            deal_id = int(conn.execute(
                "INSERT INTO deals (customer_id, stage, amount, created_at, updated_at)"
                " VALUES (?, 'won', 8800, ?, ?)",
                (customer_id, now, now),
            ).lastrowid)
            order_id = int(conn.execute(
                "INSERT INTO orders"
                " (order_no, customer_id, deal_id, amount, status, shipped_at,"
                " created_at, updated_at)"
                " VALUES ('SO-V2-022', ?, ?, 8800, 'shipped', ?, ?, ?)",
                (customer_id, deal_id, now, now, now),
            ).lastrowid)
            conn.execute(
                "INSERT INTO dict_items"
                " (dict_code, key, label, sort, enabled, created_at, updated_at)"
                " VALUES ('order_status', 'shipped', '已发货', 7, 1, ?, ?)",
                (now, now),
            )
            conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_022'")
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            status, completed_at = conn.execute(
                "SELECT status, completed_at FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            log_count = conn.execute(
                "SELECT COUNT(*) FROM order_status_log"
                " WHERE order_id = ? AND from_status = 'shipped'"
                " AND to_status = 'completed'",
                (order_id,),
            ).fetchone()[0]
            dict_deleted = conn.execute(
                "SELECT is_delete FROM dict_items"
                " WHERE dict_code = 'order_status' AND key = 'shipped'",
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(status, "completed")
        self.assertIsNotNone(completed_at)
        self.assertEqual(log_count, 1)
        self.assertEqual(dict_deleted, 1)

    def test_v2_023_adds_external_api_schema_and_active_user_default(self):
        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            user_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(users)")
            }
            lead_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(leads)")
            }
            token_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(api_tokens)")
            }
            user_active = conn.execute(
                "SELECT is_active FROM users WHERE username = 'chen'"
            ).fetchone()[0]
            api_source = conn.execute(
                "SELECT label, enabled FROM dict_items"
                " WHERE dict_code = 'customer_source' AND key = 'api'"
                " AND is_delete = 0"
            ).fetchone()
            version = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 'v2_023'"
            ).fetchone()
            token_fks = list(conn.execute("PRAGMA foreign_key_list(api_tokens)"))
            now = "2026-11-14T00:00:00Z"
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = 'chen'"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO api_tokens"
                " (name, token, user_id, created_at, updated_at)"
                " VALUES ('audit', 'audit-token', ?, ?, ?)",
                (user_id, now, now),
            )
            token_audit = conn.execute(
                "SELECT create_time, update_time, is_delete"
                " FROM api_tokens WHERE token = 'audit-token'"
            ).fetchone()
        finally:
            conn.close()

        self.assertIn("is_active", user_columns)
        self.assertEqual(user_active, 1)
        self.assertIn("created_by", lead_columns)
        self.assertTrue(
            {
                "name", "token", "user_id", "expires_at", "revoked_at",
                "created_at", "updated_at", "create_time", "update_time", "is_delete",
            }
            <= token_columns
        )
        self.assertEqual(api_source, ("API", 1))
        self.assertIsNotNone(version)
        self.assertEqual(token_fks, [])
        self.assertTrue(token_audit[0])
        self.assertTrue(token_audit[1])
        self.assertEqual(token_audit[2], 0)

    def test_v2_024_adds_follow_up_creator_without_rewriting_history(self):
        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(follow_ups)")
            }
            conn.execute(
                "INSERT INTO follow_ups (object_type, object_id, customer_id, content, created_at)"
                " VALUES ('customer', 1, 1, '迁移后普通跟进', '2026-11-14T00:00:00Z')"
            )
            historical = conn.execute(
                "SELECT created_by FROM follow_ups ORDER BY id"
            ).fetchall()
            version = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 'v2_024'"
            ).fetchone()
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()

        self.assertIn("created_by", columns)
        self.assertTrue(historical)
        self.assertTrue(all(row[0] is None for row in historical))
        self.assertIsNotNone(version)
        self.assertEqual(user_version, 23)

    def test_aftersale_relation_column_exists(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(aftersales)")
            }
        finally:
            conn.close()
        self.assertIn("related_aftersale_id", columns)

    def test_product_catalog_seeded_once(self):
        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)
        self.assertEqual(_rows(self.db, "products"), 123)

    def test_migration_clear_data(self):
        run_migrations(self.db, backup=False, verbose=False)
        for t in ("customers", "deals", "follow_ups", "tags"):
            self.assertEqual(_rows(self.db, t), 0, f"Q2：{t} 应被清空")
        self.assertEqual(_rows(self.db, "users"), 1, "Q2：users 必须保留")

    def test_every_table_has_standard_audit_and_soft_delete_columns(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            tables = [
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master"
                    " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for table in tables:
                columns = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                }
                self.assertTrue(
                    {"create_time", "update_time", "is_delete"} <= columns,
                    f"{table} 缺标准列：{columns}",
                )
            index = conn.execute(
                "SELECT 1 FROM sqlite_master"
                " WHERE type = 'index' AND name = 'uq_leads_phone_active'"
            ).fetchone()
            self.assertIsNotNone(index, "线索电话必须建立未删除记录唯一索引")
        finally:
            conn.close()

    def test_standard_timestamps_are_filled_by_trigger(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            conn.execute(
                "INSERT INTO tags (name, created_at)"
                " VALUES ('标准字段', '2026-10-31T00:00:00Z')"
            )
            row = conn.execute(
                "SELECT create_time, update_time, is_delete FROM tags"
                " WHERE name = '标准字段'"
            ).fetchone()
        finally:
            conn.commit()
            conn.close()
        self.assertTrue(row[0])
        self.assertTrue(row[1])
        self.assertEqual(row[2], 0)

    def test_database_enforces_unique_active_lead_phone(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        now = "2026-10-31T00:00:00Z"
        try:
            conn.execute(
                "INSERT INTO leads (name, phone, source, status, created_at, updated_at)"
                " VALUES ('电话一','13800138000','wechat','new',?,?)",
                (now, now),
            )
            conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO leads (name, phone, source, status, created_at, updated_at)"
                    " VALUES ('电话二','13800138000','wechat','new',?,?)",
                    (now, now),
                )
        finally:
            conn.close()

    def test_v2_019_backfills_contact_and_drops_redundant_table(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        now = "2026-11-01T00:00:00Z"
        try:
            customer_id = int(conn.execute(
                "INSERT INTO customers"
                " (name, phone, wechat, customer_type, company_name, created_at, updated_at)"
                " VALUES ('中电金信','18366326404','游戏520','company','中电金信',?,?)",
                (now, now),
            ).lastrowid)
            conn.execute(
                """
                CREATE TABLE customer_contacts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  customer_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  phone TEXT,
                  wechat TEXT,
                  is_primary INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  create_time TEXT NOT NULL DEFAULT '',
                  update_time TEXT NOT NULL DEFAULT '',
                  is_delete INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "INSERT INTO customer_contacts"
                " (customer_id, name, phone, wechat, is_primary, created_at, updated_at)"
                " VALUES (?, '陈明', '18366326404', '游戏520', 1, ?, ?)",
                (customer_id, now, now),
            )
            conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_019'")
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            row = conn.execute(
                "SELECT name, company_name, phone, wechat FROM customers WHERE id = ?",
                (customer_id,),
            ).fetchone()
            dropped = conn.execute(
                "SELECT 1 FROM sqlite_master"
                " WHERE type = 'table' AND name = 'customer_contacts'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, ("中电金信", "陈明", "18366326404", "游戏520"))
        self.assertIsNone(dropped)

    def test_v2_007_normalizes_existing_spec_separators(self):
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        now = "2026-11-01T00:00:00Z"
        try:
            customer_id = int(conn.execute(
                "INSERT INTO customers (name, customer_type, created_at, updated_at)"
                " VALUES ('尺寸客户','personal',?,?)",
                (now, now),
            ).lastrowid)
            deal_id = int(conn.execute(
                "INSERT INTO deals"
                " (customer_id, spec, amount, stage, created_at, updated_at)"
                " VALUES (?, '1200x2400', 1000, 'quote', ?, ?)",
                (customer_id, now, now),
            ).lastrowid)
            conn.execute(
                "INSERT INTO orders"
                " (order_no, customer_id, deal_id, spec, amount, status, created_at, updated_at)"
                " VALUES ('SO-SPEC-001', ?, ?, '1300×2500', 1000, 'pending_payment', ?, ?)",
                (customer_id, deal_id, now, now),
            )
            conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_007'")
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        run_migrations(self.db, backup=False, verbose=False)

        conn = sqlite3.connect(str(self.db))
        try:
            deal_spec = conn.execute(
                "SELECT spec FROM deals WHERE id = ?", (deal_id,)
            ).fetchone()[0]
            order_spec = conn.execute(
                "SELECT spec FROM orders WHERE deal_id = ?", (deal_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(deal_spec, "1200*2400")
        self.assertEqual(order_spec, "1300*2500")


if __name__ == "__main__":
    unittest.main()

class TestMigrationsIdempotent(unittest.TestCase):
    """R1 Blocker B1：值域迁移必须只跑一次，二次启动不得改写业务数据。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "idem.db"
        ensure_schema(self.db)
        run_migrations(self.db, backup=False, verbose=False)

    def tearDown(self):
        self._tmp.cleanup()

    def _stage(self) -> str:
        conn = sqlite3.connect(str(self.db))
        try:
            return conn.execute("SELECT stage FROM deals WHERE id = ?", (self._deal_id,)).fetchone()[0]
        finally:
            conn.close()

    def test_confirmed_quote_restored_from_legacy_void_state(self):
        conn = sqlite3.connect(str(self.db))
        now = "2026-11-02T10:00:00Z"
        try:
            customer_id = conn.execute(
                "INSERT INTO customers (name, created_at, updated_at) VALUES (?, ?, ?)",
                ("确认报价客户", now, now),
            ).lastrowid
            deal_id = conn.execute(
                "INSERT INTO deals (customer_id, amount, stage, created_at, updated_at)"
                " VALUES (?, 1000, 'won', ?, ?)",
                (customer_id, now, now),
            ).lastrowid
            quote_id = conn.execute(
                "INSERT INTO deal_quotes"
                " (quote_no, deal_id, customer_id, title, status, amount,"
                " confirmed_at, created_at, updated_at)"
                " VALUES ('QT-LEGACY-VOID', ?, ?, '已确认报价', 'void', 1000, ?, ?, ?)",
                (deal_id, customer_id, now, now, now),
            ).lastrowid
            conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_016'")
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            status = conn.execute(
                "SELECT status FROM deal_quotes WHERE id = ?", (quote_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "confirmed")

    def test_domain_migration_runs_once(self):
        conn = sqlite3.connect(str(self.db))
        now = "2026-10-31T10:00:00Z"
        conn.execute(
            "INSERT INTO customers (name, customer_type, created_at, updated_at)"
            " VALUES ('张三','personal',?,?)", (now, now)
        )
        cur = conn.execute(
            "INSERT INTO deals (customer_id, amount, stage, created_at, updated_at)"
            " VALUES (1, 12000, 'confirm', ?, ?)", (now, now)
        )
        self._deal_id = int(cur.lastrowid)
        conn.commit()
        conn.close()

        # 二次启动（lifespan 每次都会跑迁移）
        run_migrations(self.db, backup=False, verbose=False)
        self.assertEqual(self._stage(), "confirm", "「待客户确认」不能被二次迁移改写成「报价」")

        run_migrations(self.db, backup=False, verbose=False)
        self.assertEqual(self._stage(), "confirm")

    def test_seed_not_duplicated(self):
        conn = sqlite3.connect(str(self.db))
        try:
            first = conn.execute("SELECT COUNT(*) FROM dict_items").fetchone()[0]
        finally:
            conn.close()
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            second = conn.execute("SELECT COUNT(*) FROM dict_items").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(first, second, "字典种子不能重复插入")

    def test_seed_adds_new_sources_without_overwriting_renames(self):
        conn = sqlite3.connect(str(self.db))
        try:
            conn.execute(
                "DELETE FROM dict_items WHERE dict_code = 'customer_source' AND key = 'video_account'"
            )
            conn.execute(
                "UPDATE dict_items SET label = '私域微信'"
                " WHERE dict_code = 'customer_source' AND key = 'wechat'"
            )
            conn.commit()
        finally:
            conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            labels = dict(
                conn.execute(
                    "SELECT key, label FROM dict_items"
                    " WHERE dict_code = 'customer_source' AND key IN ('wechat', 'video_account', 'xianyu')"
                ).fetchall()
            )
        finally:
            conn.close()
        self.assertEqual(labels["video_account"], "视频号")
        self.assertEqual(labels["xianyu"], "咸鱼")
        self.assertEqual(labels["wechat"], "私域微信", "补种不能覆盖用户改过的显示名")

    def test_following_backfill_runs_once_without_overwriting_later_status(self):
        conn = sqlite3.connect(str(self.db))
        now = "2026-10-31T10:00:00Z"
        cur = conn.execute(
            "INSERT INTO leads (name, phone, source, status, created_at, updated_at)"
            " VALUES ('回填线索','13800138000','wechat','new',?,?)",
            (now, now),
        )
        lead_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO follow_ups"
            " (object_type, object_id, kind, content, created_at)"
            " VALUES ('lead', ?, 'follow', '首次跟进', ?)",
            (lead_id, now),
        )
        # 模拟从 v2_003 升级：数据已经存在，但 v2_004 尚未执行。
        conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_004'")
        conn.commit()
        conn.close()

        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            status = conn.execute(
                "SELECT status FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "following")

        conn = sqlite3.connect(str(self.db))
        conn.execute("UPDATE leads SET status = 'invalid' WHERE id = ?", (lead_id,))
        conn.commit()
        conn.close()
        run_migrations(self.db, backup=False, verbose=False)
        conn = sqlite3.connect(str(self.db))
        try:
            status = conn.execute(
                "SELECT status FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "invalid")


if __name__ == '__main__':
    unittest.main()
