"""右上角用户菜单：个人信息 / 修改密码（PLANNER-V3 追加 · v2_003）。"""
from __future__ import annotations

import unittest

from tests._util import ApiTestCase


class ProfileTest(ApiTestCase):
    def test_me_returns_display_name(self):
        me = self.client.get("/api/crm/me").json()
        self.assertEqual(me["username"], "chen")
        self.assertTrue(me["display_name"], "显示名默认回落用户名")

    def test_update_display_name(self):
        resp = self.client.put("/api/crm/me/profile", json={"display_name": "陈明"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["display_name"], "陈明")
        self.assertEqual(self.client.get("/api/crm/me").json()["display_name"], "陈明")

    def test_username_is_read_only(self):
        resp = self.client.put(
            "/api/crm/me/profile",
            json={"username": "chen2", "display_name": "陈明"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["username"], "chen")
        self.assertEqual(resp.json()["display_name"], "陈明")
        me = self.client.get("/api/crm/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["username"], "chen")

    def test_change_password_flow(self):
        bad = self.client.put(
            "/api/crm/me/password",
            json={"old_password": "wrong", "new_password": "newpass123"},
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "old_password_invalid")

        same = self.client.put(
            "/api/crm/me/password",
            json={"old_password": "test123", "new_password": "test123"},
        )
        self.assertEqual(same.status_code, 400, same.text)

        ok = self.client.put(
            "/api/crm/me/password",
            json={"old_password": "test123", "new_password": "newpass123"},
        )
        self.assertEqual(ok.status_code, 200, ok.text)

        # 新密码能登录，旧密码不行
        self.client.cookies.clear()
        self.assertEqual(
            self.client.post(
                "/api/crm/login", json={"username": "chen", "password": "test123"}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/crm/login", json={"username": "chen", "password": "newpass123"}
            ).status_code,
            200,
        )
        # 还原密码，避免污染同库后续用例（测试库共享）
        self.assertEqual(
            self.client.put(
                "/api/crm/me/password",
                json={"old_password": "newpass123", "new_password": "test123"},
            ).status_code,
            200,
        )

    def test_requires_login(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/crm/me").status_code, 401)
        self.assertEqual(
            self.client.put("/api/crm/me/profile", json={"display_name": "x"}).status_code, 401
        )


if __name__ == "__main__":
    unittest.main()
