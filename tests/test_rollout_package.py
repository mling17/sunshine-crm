"""外部 API 生产更新包：迁移收敛、审计与上线验证。"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sqlglot

from tests import _bootstrap  # noqa: F401  —— 必须先初始化隔离 DB/上传目录

from app.migrations import run_migrations
from app.mysql_schema import STANDARD_COLUMNS, TABLE_DDL
from app.schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "ops" / "sql"


def _schema_signature(db: Path) -> dict[str, object]:
    conn = sqlite3.connect(str(db))
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                " ORDER BY name"
            )
        ]
        columns = {
            table: sorted(
                (row[1], row[2], row[3], row[4], row[5])
                for row in conn.execute(f"PRAGMA table_info('{table}')")
            )
            for table in tables
        }
        indexes = {
            table: sorted(
                (row[1], row[2])
                for row in conn.execute(f"PRAGMA index_list('{table}')")
                if not row[1].startswith("sqlite_autoindex_")
            )
            for table in tables
        }
        triggers = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type = 'trigger' ORDER BY name"
            )
        ]
        api_source = conn.execute(
            "SELECT key, label, enabled, is_delete FROM dict_items"
            " WHERE dict_code = 'customer_source' AND key = 'api'"
        ).fetchone()
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations"
                " WHERE version IN ('v2_023', 'v2_024', 'v2_025')"
                " ORDER BY version"
            )
        ]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    return {
        "tables": tables,
        "columns": columns,
        "indexes": indexes,
        "triggers": triggers,
        "api_source": api_source,
        "versions": versions,
        "user_version": user_version,
    }


def _downgrade_external_schema_to_v2_022(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("ALTER TABLE follow_ups DROP COLUMN created_by")
        conn.execute("ALTER TABLE leads DROP COLUMN created_by")
        conn.execute("ALTER TABLE users DROP COLUMN is_active")
        conn.execute("DROP TABLE api_idempotency_records")
        conn.execute("DROP TABLE api_tokens")
        conn.execute(
            "DELETE FROM dict_items"
            " WHERE dict_code = 'customer_source' AND key = 'api'"
        )
        conn.execute(
            "DELETE FROM schema_migrations"
            " WHERE version IN ('v2_023', 'v2_024', 'v2_025')"
        )
        conn.execute("PRAGMA user_version = 21")
        conn.commit()
    finally:
        conn.close()


class RolloutMigrationTest(unittest.TestCase):
    def test_consolidated_sqlite_script_converges_upgrade_to_application_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            application_db = root / "application.db"
            upgrade_db = root / "upgrade.db"

            ensure_schema(application_db)
            run_migrations(application_db, backup=False, verbose=False)
            ensure_schema(upgrade_db)
            run_migrations(upgrade_db, backup=False, verbose=False)
            _downgrade_external_schema_to_v2_022(upgrade_db)

            script = SQL / "v2_022_to_v2_025.sqlite.sql"
            self.assertTrue(script.is_file(), "缺生产用合并更新脚本")
            conn = sqlite3.connect(str(upgrade_db))
            try:
                conn.executescript(script.read_text(encoding="utf-8"))
            finally:
                conn.close()

            self.assertEqual(
                _schema_signature(upgrade_db),
                _schema_signature(application_db),
            )
            run_migrations(upgrade_db, backup=False, verbose=False)
            self.assertEqual(
                _schema_signature(upgrade_db),
                _schema_signature(application_db),
            )

            for name, db in (
                ("fresh", application_db),
                ("upgrade", upgrade_db),
            ):
                uploads = root / f"{name}-uploads"
                env = os.environ.copy()
                env.update(
                    {
                        "CRM_DB": str(db),
                        "CRM_UPLOADS": str(uploads),
                        "CRM_DB_ENGINE": "sqlite",
                        "ADMIN_PASSWORD": "rollout-fixture-password",
                    }
                )
                code = (
                    "from fastapi.testclient import TestClient;"
                    "from app.main import app;"
                    "c=TestClient(app);"
                    "c.__enter__();"
                    "r=c.get('/health');"
                    "assert r.status_code == 200, r.text;"
                    "assert r.json()['status'] == 'ok', r.text;"
                    "c.__exit__(None, None, None)"
                )
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{name} startup failed:\n{result.stdout}\n{result.stderr}",
                )

    def test_consolidated_mysql_script_covers_same_surface_without_foreign_keys(self):
        script = SQL / "v2_022_to_v2_025.mysql.sql"
        self.assertTrue(script.is_file(), "缺 MySQL 合并更新脚本")
        text = script.read_text(encoding="utf-8")
        for marker in (
            "`is_active`",
            "`created_by`",
            "`api_tokens`",
            "`api_idempotency_records`",
            "'customer_source'",
            "'api'",
            "'v2_023'",
            "'v2_024'",
            "'v2_025'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        self.assertNotIn("FOREIGN KEY", text.upper())
        self.assertNotIn(" REFERENCES ", text.upper())

        for table in ("api_tokens", "api_idempotency_records"):
            with self.subTest(table=table):
                for column in ("create_time", "update_time", "is_delete"):
                    self.assertIn(f"`{column}`", STANDARD_COLUMNS)
                self.assertIn("${STANDARD}", TABLE_DDL[table])
                self.assertIn(f"`{table}`", text)

    def test_mysql_rollout_sql_parses_through_existing_sqlglot_path(self):
        for filename in (
            "v2_022_to_v2_025.mysql.sql",
            "preflight_external_rollout.mysql.sql",
            "postcheck_external_rollout.mysql.sql",
        ):
            with self.subTest(filename=filename):
                parsed = sqlglot.parse(
                    (SQL / filename).read_text(encoding="utf-8"),
                    read="mysql",
                )
                self.assertTrue(parsed)

    def test_preflight_audit_reports_origin_and_phone_anomalies_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.db"
            ensure_schema(db)
            run_migrations(db, backup=False, verbose=False)
            now = "2026-11-14T00:00:00Z"
            conn = sqlite3.connect(str(db))
            try:
                def customer(name: str, phone: str) -> int:
                    return int(
                        conn.execute(
                            "INSERT INTO customers"
                            " (name, phone, source, created_at, updated_at)"
                            " VALUES (?, ?, 'wechat', ?, ?)",
                            (name, phone, now, now),
                        ).lastrowid
                    )

                def lead(customer_id: int, phone: str) -> int:
                    return int(
                        conn.execute(
                            "INSERT INTO leads"
                            " (name, phone, source, status, converted_customer_id,"
                            " created_at, updated_at)"
                            " VALUES ('来源线索', ?, 'wechat', 'converted', ?, ?, ?)",
                            (phone, customer_id, now, now),
                        ).lastrowid
                    )

                def deal(customer_id: int, stage: str) -> None:
                    conn.execute(
                        "INSERT INTO deals"
                        " (customer_id, stage, amount, created_at, updated_at)"
                        " VALUES (?, ?, 1000, ?, ?)",
                        (customer_id, stage, now, now),
                    )

                no_source = customer("无来源客户", "13800000001")
                no_active = customer("无活跃商机客户", "13800000002")
                lead(no_active, "13800000002")
                deal(no_active, "won")

                clean = customer("正常客户", "13800000003")
                lead(clean, "13800000003")
                deal(clean, "quote")

                mismatch = customer("电话不一致客户", "13800000004")
                lead(mismatch, "13900000004")
                deal(mismatch, "quote")

                multiple = customer("多来源客户", "13800000005")
                lead(multiple, "13800000005")
                lead(multiple, "13900000005")
                deal(multiple, "quote")
                conn.commit()
            finally:
                conn.close()

            script = SQL / "preflight_external_rollout.sqlite.sql"
            self.assertTrue(script.is_file(), "缺 SQLite preflight 审计脚本")
            text = script.read_text(encoding="utf-8").upper()
            self.assertNotRegex(
                text,
                re.compile(
                    r"(?m)^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|BEGIN|COMMIT)\b"
                ),
            )

            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    script.read_text(encoding="utf-8")
                ).fetchall()
                counts = {
                    row["check_code"]: row["affected_count"] for row in rows
                }
                customer_count = conn.execute(
                    "SELECT COUNT(*) FROM customers"
                ).fetchone()[0]
                lead_count = conn.execute(
                    "SELECT COUNT(*) FROM leads"
                ).fetchone()[0]
            finally:
                conn.close()

            self.assertEqual(
                counts,
                {
                    "customer_without_source_lead": 1,
                    "customer_without_active_opportunity": 2,
                    "source_phone_mismatch": 2,
                    "multiple_source_leads": 1,
                },
            )
            self.assertEqual(customer_count, 5)
            self.assertEqual(lead_count, 5)

    def test_postcheck_verifies_rollout_contract_and_invariants(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "postcheck.db"
            ensure_schema(db)
            run_migrations(db, backup=False, verbose=False)
            now = "2026-11-14T00:00:00Z"
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            try:
                user_id = int(
                    conn.execute(
                        "INSERT INTO users"
                        " (username, password_hash, is_active, created_at)"
                        " VALUES ('rollout-user', 'x', 1, ?)",
                        (now,),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO api_tokens"
                    " (name, token, user_id, created_at, updated_at)"
                    " VALUES ('rollout-token', 'fixture-only-token', ?, ?, ?)",
                    (user_id, now, now),
                )
                conn.commit()

                script = SQL / "postcheck_external_rollout.sqlite.sql"
                self.assertTrue(script.is_file(), "缺 SQLite postcheck 验证脚本")
                text = script.read_text(encoding="utf-8").upper()
                self.assertNotRegex(
                    text,
                    re.compile(
                        r"(?m)^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|BEGIN|COMMIT)\b"
                    ),
                )
                rows = conn.execute(script.read_text(encoding="utf-8")).fetchall()
                checks = {row["check_code"]: row["status"] for row in rows}
            finally:
                conn.close()

            self.assertTrue(checks)
            self.assertEqual(
                {code for code, status in checks.items() if status != "PASS"},
                set(),
            )
            self.assertTrue(
                {
                    "schema_version",
                    "api_tokens_contract",
                    "api_tokens_audit",
                    "api_tokens_no_fk",
                    "api_idempotency_contract",
                    "api_idempotency_audit",
                    "api_idempotency_no_fk",
                    "customer_source_api",
                    "active_api_token",
                    "customer_without_source_lead",
                    "customer_without_active_opportunity",
                    "source_phone_mismatch",
                    "multiple_source_leads",
                }
                <= set(checks)
            )

    def test_postcheck_fails_when_no_active_api_token_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "postcheck-no-token.db"
            ensure_schema(db)
            run_migrations(db, backup=False, verbose=False)
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    (
                        SQL / "postcheck_external_rollout.sqlite.sql"
                    ).read_text(encoding="utf-8")
                ).fetchall()
                checks = {row["check_code"]: row["status"] for row in rows}
            finally:
                conn.close()
            self.assertEqual(checks["active_api_token"], "FAIL")

    def test_rollout_runbook_documents_order_backup_and_rollback_boundary(self):
        rollout = ROOT / "ops" / "ROLLOUT-EXTERNAL-API.md"
        self.assertTrue(rollout.is_file(), "缺外部 API 上线操作手册")
        text = rollout.read_text(encoding="utf-8")
        for marker in (
            "preflight_external_rollout",
            "v2_022_to_v2_025",
            "api_token_init",
            "postcheck_external_rollout",
            "一次性",
            "备份",
            "回滚",
            "恢复",
            "PASS",
            "schema_migrations",
            "v2_023",
            "v2_024",
            "v2_025",
            "GET /health",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_deployment_assets_use_placeholders_not_concrete_tokens(self):
        files = list(SQL.glob("*.sql")) + [
            ROOT / "ops" / "ROLLOUT-EXTERNAL-API.md",
            ROOT / "docs" / "EXTERNAL-API.md",
        ]
        forbidden_literals = (
            "test-token-0001",
            "fixture-token-value",
            "audit-token",
            "followup-token",
            "idempotency-token",
        )
        for path in files:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                for literal in forbidden_literals:
                    self.assertNotIn(literal, text)
                self.assertNotRegex(
                    text,
                    re.compile(r"(?i)authorization\s*:\s*bearer\s+[a-z0-9_-]{24,}"),
                )

    def test_external_guide_is_consolidated_for_all_three_endpoints(self):
        text = (
            ROOT / "docs" / "EXTERNAL-API.md"
        ).read_text(encoding="utf-8")
        for marker in (
            "POST /api/external/v1/leads",
            "POST /api/external/v1/follow-ups",
            "POST /api/external/v1/leads/phone-check",
            "Authorization: Bearer",
            "Idempotency-Key",
            "multipart/form-data",
            "10 个",
            "20MB",
            "invalid_phone",
            "duplicate_contact",
            "phone_not_found",
            "ambiguous_phone",
            "lead_closed",
            "idempotency_conflict",
            "invalid_idempotency_key",
            "401",
            "409",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
