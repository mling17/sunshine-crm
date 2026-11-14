"""外部线索 API：Bearer Token 鉴权与新增线索契约。"""

from __future__ import annotations

import unittest

from tests._util import ApiTestCase, insert_customer

from app.db import db_conn
from app.security import now_iso


class ExternalLeadApiTest(ApiTestCase):
    def issue_token(
        self,
        token: str = "test-token-0001",
        *,
        username: str = "chen",
        expires_at: str | None = None,
        revoked_at: str | None = None,
        user_active: bool = True,
    ) -> int:
        now = now_iso()
        with db_conn() as conn:
            user = conn.execute(
                "SELECT id FROM users WHERE username = ? AND is_delete = 0",
                (username,),
            ).fetchone()
            conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if user_active else 0, user["id"]),
            )
            cur = conn.execute(
                """
                INSERT INTO api_tokens
                    (name, token, user_id, expires_at, revoked_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("tests", token, user["id"], expires_at, revoked_at, now, now),
            )
            return int(cur.lastrowid or 0)

    def test_phone_only_lead_uses_bearer_token_and_records_creator(self):
        token_id = self.issue_token()

        resp = self.client.post(
            "/api/external/v1/leads",
            headers={"Authorization": "Bearer test-token-0001"},
            json={"phone": "+86 (138) 0013-8000"},
        )

        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["phone"], "13800138000")
        self.assertEqual(body["source"], "api")
        self.assertEqual(body["lead_type"], "other")
        self.assertEqual(body["status"], "new")
        self.assertIsNone(body["name"])
        self.assertIsNone(body["intent_level"])
        self.assertEqual(body["tags"], [])

        with db_conn() as conn:
            row = conn.execute(
                "SELECT l.phone, l.source, l.lead_type, l.status, l.created_by,"
                " t.id AS token_id, t.user_id"
                " FROM leads l JOIN api_tokens t ON t.id = ?"
                " WHERE l.id = ?",
                (token_id, body["id"]),
            ).fetchone()
        self.assertEqual(
            (
                row["phone"],
                row["source"],
                row["lead_type"],
                row["status"],
                row["created_by"],
            ),
            ("13800138000", "api", "other", "new", row["user_id"]),
        )
        self.assertEqual(body["created_by"], row["user_id"])

    def test_external_auth_failures_are_indistinguishable_and_do_not_write(self):
        self.issue_token("expired-token", expires_at="2000-01-01T00:00:00Z")
        self.issue_token("revoked-token", revoked_at="2026-01-01T00:00:00Z")
        self.issue_token("deleted-token")
        self.issue_token("inactive-token", user_active=False)
        with db_conn() as conn:
            conn.execute(
                "UPDATE api_tokens SET is_delete = 1 WHERE token = 'deleted-token'"
            )

        cases = [
            ("missing", {}),
            ("malformed", {"Authorization": "Token abc"}),
            ("unknown", {"Authorization": "Bearer not-issued"}),
            ("expired", {"Authorization": "Bearer expired-token"}),
            ("revoked", {"Authorization": "Bearer revoked-token"}),
            ("deleted", {"Authorization": "Bearer deleted-token"}),
            ("inactive-user", {"Authorization": "Bearer inactive-token"}),
            # 已登录的 Cookie 不能替代外部 Token。
            ("cookie-only", None),
        ]
        for name, headers in cases:
            with self.subTest(name=name):
                resp = self.client.post(
                    "/api/external/v1/leads",
                    headers=headers,
                    json={"phone": "13800138000"},
                )
                self.assertEqual(resp.status_code, 401, resp.text)
                self.assertEqual(resp.json(), {"detail": "认证失败", "code": "unauthorized"})

        with db_conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0], 0)

    def test_optional_business_fields_are_persisted_and_tags_are_normalized(self):
        self.issue_token()
        resp = self.client.post(
            "/api/external/v1/leads",
            headers={"Authorization": "Bearer test-token-0001"},
            json={
                "phone": "86 139-0013-9000",
                "name": "  王经理  ",
                "wechat": "  wang-biz  ",
                "lead_type": "company",
                "company_name": "  海景装饰  ",
                "source_other": "  展会二维码  ",
                "location": "  青岛市北区  ",
                "note": "  展会上沟通  ",
                "intent_level": "high",
                "owner": "  销售甲  ",
                "tags": [" 重点 ", "重点", "展会"],
            },
        )

        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["phone"], "13900139000")
        self.assertEqual(body["name"], "王经理")
        self.assertEqual(body["wechat"], "wang-biz")
        self.assertEqual(body["lead_type"], "company")
        self.assertEqual(body["company_name"], "海景装饰")
        self.assertEqual(body["source_other"], "展会二维码")
        self.assertEqual(body["location"], "青岛市北区")
        self.assertEqual(body["note"], "展会上沟通")
        self.assertEqual(body["intent_level"], "high")
        self.assertEqual(body["owner"], "销售甲")
        self.assertEqual(body["tags"], ["重点", "展会"])
        self.assertEqual(body["source"], "api")

    def test_invalid_phone_and_server_managed_or_unknown_fields_are_rejected(self):
        self.issue_token()
        headers = {"Authorization": "Bearer test-token-0001"}

        invalid_phone = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "12345"},
        )
        self.assertEqual(invalid_phone.status_code, 400, invalid_phone.text)
        self.assertEqual(invalid_phone.json()["code"], "invalid_phone")

        for field, value in (
            ("id", 9),
            ("status", "converted"),
            ("source", "wechat"),
            ("created_by", 2),
            ("created_at", "2026-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field):
                resp = self.client.post(
                    "/api/external/v1/leads",
                    headers=headers,
                    json={"phone": "13700137000", field: value},
                )
                self.assertEqual(resp.status_code, 400, resp.text)
                self.assertEqual(resp.json()["code"], "validation_failed")

        with db_conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0], 0)

    def test_active_lead_and_customer_conflicts_return_summary_but_soft_deleted_do_not(self):
        self.issue_token()
        headers = {"Authorization": "Bearer test-token-0001"}

        first = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "13800138000", "name": "已有线索"},
        )
        self.assertEqual(first.status_code, 201, first.text)
        lead_duplicate = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "+86 138-0013-8000"},
        )
        self.assertEqual(lead_duplicate.status_code, 409, lead_duplicate.text)
        self.assertEqual(lead_duplicate.json()["code"], "duplicate_contact")
        self.assertEqual(
            lead_duplicate.json()["duplicate_hint"]["object_type"],
            "lead",
        )
        self.assertEqual(
            lead_duplicate.json()["duplicate_hint"]["status"],
            "new",
        )

        customer_id = insert_customer(name="已有客户", phone="13900139000")
        customer_duplicate = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "139 0013 9000"},
        )
        self.assertEqual(customer_duplicate.status_code, 409, customer_duplicate.text)
        self.assertEqual(
            customer_duplicate.json()["duplicate_hint"]["object_type"],
            "customer",
        )
        self.assertEqual(
            customer_duplicate.json()["duplicate_hint"]["object_id"],
            int(customer_id),
        )

        now = now_iso()
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO leads"
                " (name, phone, source, status, is_delete, created_at, updated_at)"
                " VALUES ('已删除线索', '13700137000', 'wechat', 'new', 1, ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO customers"
                " (name, phone, customer_type, source, is_delete, created_at, updated_at)"
                " VALUES ('已删除客户', '13600136000', 'personal', 'wechat', 1, ?, ?)",
                (now, now),
            )

        for phone in ("13700137000", "13600136000"):
            with self.subTest(phone=phone):
                resp = self.client.post(
                    "/api/external/v1/leads",
                    headers=headers,
                    json={"phone": phone},
                )
                self.assertEqual(resp.status_code, 201, resp.text)

    def test_cookie_authenticated_lead_creation_records_current_user(self):
        resp = self.client.post(
            "/api/crm/leads",
            json={
                "name": "页面创建线索",
                "phone": "13500135000",
                "source": "wechat",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        with db_conn() as conn:
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = 'chen'"
            ).fetchone()["id"]
            row = conn.execute(
                "SELECT created_by FROM leads WHERE id = ?",
                (body["id"],),
            ).fetchone()
        self.assertEqual(body["created_by"], user_id)
        self.assertEqual(row["created_by"], user_id)


if __name__ == "__main__":
    unittest.main()
