"""T1：健康检查 + 建表 + 种子用户。"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from tests import _bootstrap  # noqa: F401  —— 必须最先 import，设置临时 DB 环境变量

from fastapi.testclient import TestClient

from app.main import app


class HealthTest(unittest.TestCase):
    def setUp(self):
        # with TestClient(...) 会触发 lifespan：建表、建上传目录、种种子用户
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_health_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(Path(body["db"]).resolve(), _bootstrap.TEST_DB.resolve())
        self.assertEqual(body["db_engine"], "sqlite")
        self.assertTrue(body["ts"])

    def test_schema_and_seed_user(self):
        # 1) 计划 §4 要求的表一张都不能少
        conn = sqlite3.connect(str(_bootstrap.TEST_DB))
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            expected = {
                "users",
                "sessions",
                "customers",
                "deals",
                "follow_ups",
                "attachments",
                "import_log",
                "tags",
                "customer_tags",
            }
            self.assertTrue(expected.issubset(tables), f"缺表: {expected - tables}")

            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            expected_idx = {
                "idx_customers_name",
                "idx_customers_phone",
                "idx_deals_customer",
                "idx_deals_stage",
                "idx_deals_closed",
                "idx_fu_customer",
                "idx_fu_next_date",
                "idx_att_fu",
                "idx_cust_tag_c",
                "idx_cust_tag_t",
            }
            self.assertTrue(
                expected_idx.issubset(indexes), f"缺索引: {expected_idx - indexes}"
            )

            # 2) users 为空时会按 env 种一个 PBKDF2 用户
            users = conn.execute("SELECT username, password_hash FROM users").fetchall()
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0][0], "chen")
            self.assertTrue(users[0][1].startswith("$pbkdf2$200000$"))
        finally:
            conn.close()

        # 3) 上传目录已建
        self.assertTrue(Path(_bootstrap.TEST_UPLOADS).is_dir())

    def test_db_helper_contract(self):
        """app.db.db_conn 必须开外键 + row_factory=Row + 用后即关。"""
        from app.db import db_conn

        with db_conn() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertIsInstance(conn.execute("SELECT 1 AS x").fetchone(), sqlite3.Row)
            self.assertEqual(conn.execute("SELECT 1 AS x").fetchone()["x"], 1)
        # 退出 with 后连接已关闭
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
