"""外部按手机号新增跟进：匹配、附件、审计与原子失败回归。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests._util import ApiTestCase, insert_customer

from fastapi.testclient import TestClient

from app.config.settings import settings
from app.db import db_conn
from app.main import app
from app.security import now_iso

PNG = b"\x89PNG\r\n\x1a\n" + b"external-followup"


class ExternalFollowUpApiTest(ApiTestCase):
    def auth(self, token: str = "followup-token") -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def insert_lead(
        self,
        *,
        phone: str,
        name: str = "线索",
        status: str = "new",
    ) -> int:
        now = now_iso()
        with db_conn() as conn:
            cur = conn.execute(
                "INSERT INTO leads"
                " (name, phone, source, lead_type, status, created_at, updated_at)"
                " VALUES (?, ?, 'wechat', 'personal', ?, ?, ?)",
                (name, phone, status, now, now),
            )
            return int(cur.lastrowid or 0)

    def upload_paths(self) -> set[Path]:
        root = settings.uploads_path
        if not root.exists():
            return set()
        return {path for path in root.rglob("*") if path.is_file()}

    def test_customer_takes_priority_and_multiple_attachments_are_atomic(self):
        token = self.issue_external_token("followup-token")
        user_id = token["user_id"]
        customer_id = insert_customer(
            name="客户优先",
            phone="13800138000",
            location="济南",
        )
        lead_id = self.insert_lead(phone="13800138000", name="同号线索")

        resp = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={
                "phone": "+86 (138) 0013-8000",
                "content": "  客户电话沟通完成  ",
                "method": "phone",
                "next_date": "2026-12-01",
            },
            files=[
                ("attachments", ("报价.pdf", b"%PDF-1.4 quote", "application/pdf")),
                ("attachments", ("现场.png", PNG, "image/png")),
            ],
        )

        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["object_type"], "customer")
        self.assertEqual(body["object_id"], customer_id)
        self.assertEqual(body["customer_id"], customer_id)
        self.assertEqual(body["content"], "客户电话沟通完成")
        self.assertEqual(body["method"], "phone")
        self.assertEqual(body["next_date"], "2026-12-01")
        self.assertEqual(body["created_by"], user_id)
        self.assertEqual(body["photo_count"], 2)
        self.assertEqual(
            {item["file_name"] for item in body["photos"]},
            {"报价.pdf", "现场.png"},
        )
        with db_conn() as conn:
            lead_status = conn.execute(
                "SELECT status FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()["status"]
            stored = conn.execute(
                "SELECT object_type, object_id, customer_id, created_by, content"
                " FROM follow_ups WHERE id = ?",
                (body["id"],),
            ).fetchone()
        self.assertEqual(lead_status, "new")
        self.assertEqual(
            tuple(stored),
            ("customer", customer_id, customer_id, user_id, "客户电话沟通完成"),
        )

    def test_lead_fallback_creates_follow_up_and_moves_new_lead_to_following(self):
        self.issue_external_token("followup-token")
        lead_id = self.insert_lead(phone="13900139000")

        resp = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "139-0013-9000", "content": "首次电话沟通"},
        )

        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["object_type"], "lead")
        self.assertEqual(body["object_id"], lead_id)
        self.assertIsNone(body["customer_id"])
        with db_conn() as conn:
            lead = conn.execute(
                "SELECT status FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()
            follow = conn.execute(
                "SELECT created_by FROM follow_ups WHERE id = ?", (body["id"],)
            ).fetchone()
        self.assertEqual(lead["status"], "following")
        self.assertIsNotNone(follow["created_by"])

    def test_phone_matching_errors_are_stable(self):
        self.issue_external_token("followup-token")

        missing = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "13800138000", "content": "找不到"},
        )
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["code"], "phone_not_found")
        self.assertEqual(missing.json()["detail"], "13800138000手机号不存在")

        insert_customer(name="客户甲", phone="13600136000")
        insert_customer(name="客户乙", phone="13600136000")
        ambiguous_customer = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "13600136000", "content": "歧义"},
        )
        self.assertEqual(ambiguous_customer.status_code, 409, ambiguous_customer.text)
        self.assertEqual(ambiguous_customer.json()["code"], "ambiguous_phone")

        with db_conn() as conn:
            conn.execute("DELETE FROM customers")
        self.insert_lead(phone="13500135000", name="线索甲")
        self.insert_lead(phone="135-0013-5000", name="线索乙")
        ambiguous_lead = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "13500135000", "content": "歧义"},
        )
        self.assertEqual(ambiguous_lead.status_code, 409, ambiguous_lead.text)
        self.assertEqual(ambiguous_lead.json()["code"], "ambiguous_phone")

        with db_conn() as conn:
            conn.execute("DELETE FROM leads")
        self.insert_lead(phone="13700137000", status="converted")
        closed = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "13700137000", "content": "已转化"},
        )
        self.assertEqual(closed.status_code, 409, closed.text)
        self.assertEqual(closed.json()["code"], "lead_closed")

    def test_field_and_attachment_validation_happens_without_writes(self):
        self.issue_external_token("followup-token")
        lead_id = self.insert_lead(phone="13800138000")
        before_files = self.upload_paths()

        cases = [
            ({"phone": "13800138000", "content": "   "}, []),
            ({"phone": "13800138000", "content": "x" * 2001}, []),
            (
                {
                    "phone": "13800138000",
                    "content": "日期错误",
                    "next_date": "2026/12/01",
                },
                [],
            ),
            (
                {"phone": "13800138000", "content": "危险附件"},
                [("attachments", ("x.html", b"<script>x</script>", "text/html"))],
            ),
        ]
        for data, files in cases:
            with self.subTest(data=data, files=files):
                resp = self.client.post(
                    "/api/external/v1/follow-ups",
                    headers=self.auth(),
                    data=data,
                    files=files or None,
                )
                self.assertEqual(resp.status_code, 400, resp.text)

        many = [
            ("attachments", (f"{i}.txt", b"x", "text/plain"))
            for i in range(11)
        ]
        over_limit = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "13800138000", "content": "过多附件"},
            files=many,
        )
        self.assertEqual(over_limit.status_code, 400, over_limit.text)
        self.assertIn("10", over_limit.json()["detail"])

        with db_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM follow_ups WHERE object_type = 'lead'"
                " AND object_id = ?",
                (lead_id,),
            ).fetchone()[0]
            status = conn.execute(
                "SELECT status FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()["status"]
        self.assertEqual(count, 0)
        self.assertEqual(status, "new")
        self.assertEqual(self.upload_paths(), before_files)

    def test_database_failure_removes_files_written_by_request(self):
        self.issue_external_token("followup-token")
        self.insert_lead(phone="13800138000")
        before_files = self.upload_paths()
        with db_conn() as conn:
            conn.execute(
                "CREATE TRIGGER fail_attachment_insert"
                " BEFORE INSERT ON attachments"
                " BEGIN SELECT RAISE(ABORT, 'attachment insert failed'); END"
            )
        self.addCleanup(
            lambda: self._drop_trigger("fail_attachment_insert")
        )

        with TestClient(app, raise_server_exceptions=False) as error_client:
            resp = error_client.post(
                "/api/external/v1/follow-ups",
                headers=self.auth(),
                data={"phone": "13800138000", "content": "原子失败"},
                files=[("attachments", ("a.txt", b"payload", "text/plain"))],
            )

        self.assertEqual(resp.status_code, 500, resp.text)
        with db_conn() as conn:
            follow_count = conn.execute("SELECT COUNT(*) FROM follow_ups").fetchone()[0]
            attachment_count = conn.execute(
                "SELECT COUNT(*) FROM attachments"
            ).fetchone()[0]
            lead_status = conn.execute(
                "SELECT status FROM leads WHERE phone = '13800138000'"
            ).fetchone()["status"]
        self.assertEqual(follow_count, 0)
        self.assertEqual(attachment_count, 0)
        self.assertEqual(lead_status, "new")
        self.assertEqual(self.upload_paths(), before_files)

    def _drop_trigger(self, name: str) -> None:
        with db_conn() as conn:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")

    def test_token_and_cookie_authenticated_creation_record_creator(self):
        token = self.issue_external_token("followup-token")
        token_user_id = token["user_id"]
        customer_id = insert_customer(name="页面客户", phone="13800138000")

        external = self.client.post(
            "/api/external/v1/follow-ups",
            headers=self.auth(),
            data={"phone": "13800138000", "content": "外部跟进"},
        )
        self.assertEqual(external.status_code, 201, external.text)
        self.assertEqual(external.json()["created_by"], token_user_id)

        cookie = self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "customer",
                "object_id": str(customer_id),
                "content": "页面跟进",
            },
        )
        self.assertEqual(cookie.status_code, 200, cookie.text)
        with db_conn() as conn:
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = 'chen'"
            ).fetchone()["id"]
            rows = conn.execute(
                "SELECT created_by FROM follow_ups ORDER BY id"
            ).fetchall()
        self.assertEqual([row["created_by"] for row in rows], [token_user_id, user_id])

    def test_external_follow_up_requires_bearer_token(self):
        customer_id = insert_customer(name="鉴权客户", phone="13800138000")
        resp = self.client.post(
            "/api/external/v1/follow-ups",
            data={"phone": "13800138000", "content": "无 Token"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)
        self.assertEqual(resp.json(), {"detail": "认证失败", "code": "unauthorized"})
        with db_conn() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM follow_ups WHERE customer_id = ?",
                    (customer_id,),
                ).fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
