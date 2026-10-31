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
            "leads", "lead_tags", "customer_contacts", "carriers", "orders",
            "order_status_log", "aftersales", "aftersale_status_log", "schema_migrations",
            "customers", "deals", "follow_ups", "attachments",
        }
        conn = sqlite3.connect(str(self.db))
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        finally:
            conn.close()
        self.assertTrue(expected <= tables, f"缺表：{expected - tables}")
        self.assertIn("trg_fu_object_fill", triggers)

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
