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


if __name__ == "__main__":
    unittest.main()
