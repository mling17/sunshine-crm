"""外部 API 部署资产与 MySQL 定稿结构的一致性检查。"""

from __future__ import annotations

import unittest
import sqlite3
import tempfile
from pathlib import Path

from app.migrations import run_migrations
from app.schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "ops" / "sql"


class ExternalApiAssetsTest(unittest.TestCase):
    def test_v2_023_update_scripts_cover_external_api_schema(self):
        for filename in (
            "v2_023_external_lead_api.sqlite.sql",
            "v2_023_external_lead_api.mysql.sql",
        ):
            with self.subTest(filename=filename):
                text = (SQL / filename).read_text(encoding="utf-8")
                self.assertIn("is_active", text)
                self.assertIn("created_by", text)
                self.assertIn("api_tokens", text)
                self.assertIn("v2_023", text)
                self.assertIn("customer_source", text)
                self.assertNotIn("FOREIGN KEY", text.upper())
                self.assertNotIn(" REFERENCES ", text.upper())

    def test_token_initialization_templates_use_placeholders(self):
        for filename in (
            "api_token_init.sqlite.template.sql",
            "api_token_init.mysql.template.sql",
        ):
            with self.subTest(filename=filename):
                text = (SQL / filename).read_text(encoding="utf-8")
                self.assertIn("{{TOKEN_VALUE}}", text)
                self.assertIn("{{BOUND_USERNAME}}", text)
                self.assertIn("{{EXPIRES_AT_SQL_LITERAL_OR_NULL}}", text)
                self.assertIn("api_tokens", text)
                self.assertNotIn("test-token-0001", text)

    def test_sqlite_v2_023_script_converges_with_application_migrations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "upgrade.db"
            ensure_schema(db)
            run_migrations(db, backup=False, verbose=False)
            conn = sqlite3.connect(str(db))
            try:
                conn.execute("ALTER TABLE users DROP COLUMN is_active")
                conn.execute("ALTER TABLE leads DROP COLUMN created_by")
                conn.execute("DROP TABLE api_tokens")
                conn.execute(
                    "DELETE FROM dict_items"
                    " WHERE dict_code = 'customer_source' AND key = 'api'"
                )
                conn.execute("DELETE FROM schema_migrations WHERE version = 'v2_023'")
                conn.execute("PRAGMA user_version = 21")
                conn.executescript(
                    (SQL / "v2_023_external_lead_api.sqlite.sql").read_text(
                        encoding="utf-8"
                    )
                )
                user_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(users)")
                }
                lead_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(leads)")
                }
                token_table = conn.execute(
                    "SELECT 1 FROM sqlite_master"
                    " WHERE type = 'table' AND name = 'api_tokens'"
                ).fetchone()
            finally:
                conn.close()

            self.assertIn("is_active", user_columns)
            self.assertIn("created_by", lead_columns)
            self.assertIsNotNone(token_table)
            run_migrations(db, backup=False, verbose=False)

            template = (
                SQL / "api_token_init.sqlite.template.sql"
            ).read_text(encoding="utf-8")
            template = (
                template.replace("{{TOKEN_NAME}}", "fixture-token")
                .replace("{{TOKEN_VALUE}}", "fixture-token-value")
                .replace("{{BOUND_USERNAME}}", "chen")
                .replace("{{EXPIRES_AT_SQL_LITERAL_OR_NULL}}", "NULL")
            )
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "INSERT INTO users"
                    " (username, password_hash, is_active, created_at)"
                    " VALUES ('chen', 'x', 1, '2026-11-14T00:00:00Z')"
                )
                conn.executescript(template)
                token = conn.execute(
                    "SELECT name, token, created_at, create_time"
                    " FROM api_tokens WHERE token = 'fixture-token-value'"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(token[0], "fixture-token")
            self.assertTrue(token[2])
            self.assertTrue(token[3])


if __name__ == "__main__":
    unittest.main()
