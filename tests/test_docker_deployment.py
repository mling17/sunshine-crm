"""Docker 部署产物与独立容器运行路径的回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests import _bootstrap  # noqa: F401  —— 必须最先 import，隔离测试数据库

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


class DockerArtifactsTest(unittest.TestCase):
    def test_dockerfile_is_self_contained_and_persistent(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("COPY requirements.txt", dockerfile)
        self.assertIn("pip install --no-cache-dir -r requirements.txt", dockerfile)
        self.assertNotIn("pip install --no-cache-dir -e .", dockerfile)
        self.assertIn("COPY --chown=crm:crm app ./app", dockerfile)
        self.assertIn("COPY --chown=crm:crm static ./static", dockerfile)
        self.assertIn("ops/migrate_sqlite_to_mysql.py", dockerfile)
        self.assertIn("USER crm", dockerfile)
        self.assertIn("EXPOSE 8010", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("/opt/data/crm", dockerfile)

    def test_compose_requires_password_and_uses_named_volume(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("${ADMIN_PASSWORD:?", compose)
        self.assertNotIn("ADMIN_PASSWORD=test123", compose)
        self.assertIn("${CRM_BIND_ADDRESS:-0.0.0.0}:${CRM_PORT:-8010}:8010", compose)
        self.assertIn("crm-data:/opt/data/crm", compose)
        self.assertIn("no-new-privileges:true", compose)
        self.assertIn('CRM_DB_ENGINE: "${CRM_DB_ENGINE:-sqlite}"', compose)
        self.assertIn("mysql:8.0.36", compose)
        self.assertIn('profiles: ["mysql"]', compose)
        self.assertIn("mysql-data:/var/lib/mysql", compose)
        self.assertIn("sunshine-crm-mysql-data", compose)

    def test_docker_context_excludes_runtime_data_and_secrets(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

        for expected in (".env", ".local", "tests", "docs", "crm.db", "**/uploads"):
            self.assertIn(expected, ignore)

    def test_runtime_requirements_include_pydantic_settings(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pydantic-settings", requirements)
        self.assertIn("PyMySQL", requirements)
        self.assertIn("sqlglot", requirements)

    def test_database_operations_docs_exist(self):
        for name in (
            "DATABASE-SQLITE-TO-MYSQL.md",
            "DATABASE-MYSQL-BACKUP-RESTORE.md",
            "DATABASE-SQLITE-BACKUP-RESTORE.md",
        ):
            path = ROOT / "docs" / name
            self.assertTrue(path.is_file(), f"缺少数据库文档 {name}")
            self.assertGreater(len(path.read_text(encoding="utf-8")), 500)


class StandaloneWebTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_root_redirects_to_crm_frontend(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/crm/")

    def test_frontend_is_served_by_application(self):
        response = self.client.get("/crm/")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("天窗天幕 CRM", response.text)

        script = self.client.get("/crm/app.js")
        self.assertEqual(script.status_code, 200, script.text)
        self.assertIn("API_BASE", script.text)

    def test_frontend_api_prefix_reaches_backend_routes(self):
        response = self.client.get("/crm/api/crm/me")
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
