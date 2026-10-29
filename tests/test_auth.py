"""T2：PBKDF2 登录 / 登出 / me + 12h 会话 Cookie。"""

from __future__ import annotations

import unittest
from datetime import datetime

from tests import _bootstrap  # noqa: F401  —— 必须最先 import，设置临时 DB 环境变量

from fastapi.testclient import TestClient

from app.db import db_conn
from app.main import app

COOKIE_NAME = "crm_sid"


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AuthTest(unittest.TestCase):
    def setUp(self):
        # 每个用例一个 client：进入 with 触发 lifespan（建表 + 种子用户）
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    # 1. 未登录访问受保护接口 → 401
    def test_me_requires_login(self):
        resp = self.client.get("/api/crm/me")
        self.assertEqual(resp.status_code, 401, resp.text)

    # 2. 密码错误 → 401
    def test_login_wrong_password_returns_401(self):
        resp = self.client.post(
            "/api/crm/login", json={"username": "chen", "password": "wrong-password"}
        )
        self.assertEqual(resp.status_code, 401, resp.text)
        self.assertNotIn(COOKIE_NAME, self.client.cookies)

    # 3. 登录成功 → 200 + HttpOnly Cookie + 会话有效期 12h
    def test_login_sets_httponly_cookie(self):
        resp = self.client.post(
            "/api/crm/login", json={"username": "chen", "password": "test123"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        raw = resp.headers.get("set-cookie", "")
        self.assertIn(f"{COOKIE_NAME}=", raw, raw)
        self.assertIn("HttpOnly", raw, raw)
        self.assertIn("SameSite=lax", raw, raw)
        self.assertIn("Path=/", raw, raw)
        self.assertIn("Max-Age=43200", raw, raw)

        # 会话行必须固定 12h 过期（不滑动）
        token = self.client.cookies.get(COOKIE_NAME)
        self.assertTrue(token)
        with db_conn() as conn:
            row = conn.execute(
                "SELECT username, created_at, expires_at FROM sessions WHERE token = ?",
                (token,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["username"], "chen")
        ttl = _parse_iso(row["expires_at"]) - _parse_iso(row["created_at"])
        self.assertEqual(ttl.total_seconds(), 12 * 3600)

    # 4. 带 Cookie 访问 /me → 200 且返回用户名
    def test_me_with_cookie_returns_username(self):
        login = self.client.post(
            "/api/crm/login", json={"username": "chen", "password": "test123"}
        )
        self.assertEqual(login.status_code, 200, login.text)

        resp = self.client.get("/api/crm/me")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["username"], "chen")

    # 5. 登出后 /me → 401（会话行已删）
    def test_logout_invalidates_session(self):
        self.client.post(
            "/api/crm/login", json={"username": "chen", "password": "test123"}
        )
        self.assertEqual(self.client.get("/api/crm/me").status_code, 200)

        logout = self.client.post("/api/crm/logout")
        self.assertEqual(logout.status_code, 200, logout.text)
        self.assertEqual(self.client.get("/api/crm/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
