"""外部 API：批量校验手机号是否已在线索池。"""

from __future__ import annotations

import unittest

from tests._util import ApiTestCase, insert_customer

from app.db import db_conn
from app.security import now_iso


class ExternalPhoneCheckTest(ApiTestCase):
    ENDPOINT = "/api/external/v1/leads/phone-check"
    HEADERS = {"Authorization": "Bearer phone-check-token"}

    def insert_lead(
        self,
        phone: str,
        *,
        status: str = "new",
        is_delete: int = 0,
    ) -> int:
        now = now_iso()
        with db_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO leads
                    (name, phone, source, status, is_delete, created_at, updated_at)
                VALUES (?, ?, 'wechat', ?, ?, ?, ?)
                """,
                (f"线索-{phone}", phone, status, is_delete, now, now),
            )
            return int(cur.lastrowid or 0)

    def test_requires_bearer_token_and_rejects_cookie_only(self):
        payload = {"phones": ["13800138000"]}
        for name, headers in (
            ("missing", {}),
            ("malformed", {"Authorization": "Token wrong"}),
            ("cookie-only", None),
        ):
            with self.subTest(name=name):
                resp = self.client.post(
                    self.ENDPOINT,
                    headers=headers,
                    json=payload,
                )
                self.assertEqual(resp.status_code, 401, resp.text)
                self.assertEqual(resp.json(), {"detail": "认证失败", "code": "unauthorized"})

    def test_accepts_one_and_five_hundred_values(self):
        self.issue_external_token("phone-check-token")
        for phones in (
            ["13800138000"],
            [f"138{index:08d}" for index in range(500)],
        ):
            with self.subTest(size=len(phones)):
                resp = self.client.post(
                    self.ENDPOINT,
                    headers=self.HEADERS,
                    json={"phones": phones},
                )
                self.assertEqual(resp.status_code, 200, resp.text)
                self.assertEqual(len(resp.json()["items"]), len(phones))

    def test_rejects_empty_and_over_limit_batches(self):
        self.issue_external_token("phone-check-token")
        for phones in (
            [],
            [f"138{index:08d}" for index in range(501)],
        ):
            with self.subTest(size=len(phones)):
                resp = self.client.post(
                    self.ENDPOINT,
                    headers=self.HEADERS,
                    json={"phones": phones},
                )
                self.assertEqual(resp.status_code, 400, resp.text)
                self.assertEqual(resp.json()["code"], "validation_failed")

    def test_malformed_batch_fails_all_and_reports_zero_based_positions(self):
        self.issue_external_token("phone-check-token")
        self.insert_lead("13800138000")
        resp = self.client.post(
            self.ENDPOINT,
            headers=self.HEADERS,
            json={
                "phones": [
                    "13800138000",
                    "not-a-phone",
                    "+86 139-0013-9000",
                    "12345",
                ]
            },
        )

        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "invalid_phone")
        self.assertEqual(resp.json()["invalid_positions"], [1, 3])

    def test_non_string_batch_entries_use_the_same_invalid_phone_contract(self):
        self.issue_external_token("phone-check-token")
        resp = self.client.post(
            self.ENDPOINT,
            headers=self.HEADERS,
            json={
                "phones": [
                    None,
                    "13800138000",
                    12345,
                    {"phone": "13700137000"},
                ]
            },
        )

        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "invalid_phone")
        self.assertEqual(resp.json()["invalid_positions"], [0, 2, 3])

    def test_normalizes_and_deduplicates_in_first_occurrence_order(self):
        self.issue_external_token("phone-check-token")
        self.insert_lead("13800138000")
        self.insert_lead("13900139000")
        resp = self.client.post(
            self.ENDPOINT,
            headers=self.HEADERS,
            json={
                "phones": [
                    "+86 (139) 0013-9000",
                    "138 0013 8000",
                    "13900139000",
                    "13700137000",
                    "86 138-0013-8000",
                ]
            },
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            resp.json(),
            {
                "items": [
                    {"phone": "13900139000", "exists": True},
                    {"phone": "13800138000", "exists": True},
                    {"phone": "13700137000", "exists": False},
                ]
            },
        )

    def test_checks_active_non_deleted_leads_in_any_lifecycle_state(self):
        self.issue_external_token("phone-check-token")
        phones = {
            "13800138001": ("converted", 0),
            "13800138002": ("invalid", 0),
            "13800138003": ("new", 1),
            "13800138004": ("new", 0),
        }
        for phone, (status, is_delete) in phones.items():
            self.insert_lead(phone, status=status, is_delete=is_delete)

        resp = self.client.post(
            self.ENDPOINT,
            headers=self.HEADERS,
            json={"phones": list(phones)},
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            resp.json()["items"],
            [
                {"phone": "13800138001", "exists": True},
                {"phone": "13800138002", "exists": True},
                {"phone": "13800138003", "exists": False},
                {"phone": "13800138004", "exists": True},
            ],
        )

    def test_customer_only_match_does_not_leak_or_create_false_positive(self):
        self.issue_external_token("phone-check-token")
        insert_customer(name="历史客户", phone="13800138000")
        resp = self.client.post(
            self.ENDPOINT,
            headers=self.HEADERS,
            json={"phones": ["13800138000"]},
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body, {"items": [{"phone": "13800138000", "exists": False}]})
        self.assertEqual(set(body["items"][0]), {"phone", "exists"})


if __name__ == "__main__":
    unittest.main()
