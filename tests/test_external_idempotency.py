"""外部写接口 Idempotency-Key 契约。"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests._util import ApiTestCase, insert_customer

from app.config.settings import settings
from app.db import db_conn
from app.security import now_iso


class ExternalIdempotencyTest(ApiTestCase):
    def test_identical_lead_retry_replays_original_response_without_duplicate(self):
        self.issue_external_token("idempotency-token")
        headers = {
            "Authorization": "Bearer idempotency-token",
            "Idempotency-Key": "lead-create-001",
        }
        payload = {"phone": "+86 (138) 0013-8000", "name": "重试客户"}

        first = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json=payload,
        )
        second = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json=payload,
        )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(second.content, first.content)
        with db_conn() as conn:
            lead_count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            record = conn.execute(
                "SELECT request_hash, response_status, response_body, expires_at"
                " FROM api_idempotency_records"
                " WHERE idempotency_key = 'lead-create-001'"
            ).fetchone()
        self.assertEqual(lead_count, 1)
        self.assertEqual(len(record["request_hash"]), 64)
        self.assertEqual(record["response_status"], 201)
        self.assertIsNotNone(record["expires_at"])
        self.assertEqual(
            json.loads(record["response_body"])["id"],
            first.json()["id"],
        )

    def test_reusing_key_with_different_lead_request_returns_conflict(self):
        self.issue_external_token("idempotency-token")
        headers = {
            "Authorization": "Bearer idempotency-token",
            "Idempotency-Key": "lead-create-conflict",
        }

        first = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "13800138000", "name": "第一版"},
        )
        changed = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "13800138000", "name": "第二版"},
        )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["code"], "idempotency_conflict")
        with db_conn() as conn:
            lead_count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        self.assertEqual(lead_count, 1)

    def test_key_scope_is_isolated_by_token_and_endpoint(self):
        self.issue_external_token("idempotency-token-a")
        self.issue_external_token("idempotency-token-b")
        shared_key = "shared-scope-key"

        token_a = self.client.post(
            "/api/external/v1/leads",
            headers={
                "Authorization": "Bearer idempotency-token-a",
                "Idempotency-Key": shared_key,
            },
            json={"phone": "13800138001", "name": "Token A"},
        )
        token_b = self.client.post(
            "/api/external/v1/leads",
            headers={
                "Authorization": "Bearer idempotency-token-b",
                "Idempotency-Key": shared_key,
            },
            json={"phone": "13800138002", "name": "Token B"},
        )
        same_token_other_endpoint = self.client.post(
            "/api/external/v1/follow-ups",
            headers={
                "Authorization": "Bearer idempotency-token-a",
                "Idempotency-Key": shared_key,
            },
            data={"phone": "13800138001", "content": "同 Token 不同端点"},
        )

        self.assertEqual(token_a.status_code, 201, token_a.text)
        self.assertEqual(token_b.status_code, 201, token_b.text)
        self.assertEqual(
            same_token_other_endpoint.status_code,
            201,
            same_token_other_endpoint.text,
        )

    def test_identical_follow_up_retry_replays_without_duplicate_rows_or_files(self):
        self.issue_external_token("idempotency-token")
        customer_id = insert_customer(name="幂等客户", phone="13900139000")
        headers = {
            "Authorization": "Bearer idempotency-token",
            "Idempotency-Key": "follow-up-create-001",
        }
        form = {
            "phone": "+86 (139) 0013-9000",
            "content": "  相同跟进  ",
            "method": "phone",
            "next_date": "2026-12-02",
        }
        files = [("attachments", ("记录.txt", b"same payload", "text/plain"))]
        upload_root = Path(settings.uploads_path)
        files_before = (
            {path for path in upload_root.rglob("*") if path.is_file()}
            if upload_root.exists()
            else set()
        )

        first = self.client.post(
            "/api/external/v1/follow-ups",
            headers=headers,
            data=form,
            files=files,
        )
        second = self.client.post(
            "/api/external/v1/follow-ups",
            headers=headers,
            data=form,
            files=files,
        )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(second.content, first.content)
        with db_conn() as conn:
            follow_count = conn.execute(
                "SELECT COUNT(*) FROM follow_ups WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()[0]
            attachment_count = conn.execute(
                "SELECT COUNT(*) FROM attachments WHERE follow_up_id = ?",
                (first.json()["id"],),
            ).fetchone()[0]
        files_after = (
            {
                path
                for path in upload_root.rglob("*")
                if path.is_file()
            }
            if upload_root.exists()
            else set()
        )
        self.assertEqual(follow_count, 1)
        self.assertEqual(attachment_count, 1)
        self.assertEqual(len(files_after - files_before), 1)

    def test_reusing_follow_up_key_with_different_content_returns_conflict(self):
        self.issue_external_token("idempotency-token")
        customer_id = insert_customer(name="冲突客户", phone="13700137000")
        headers = {
            "Authorization": "Bearer idempotency-token",
            "Idempotency-Key": "follow-up-conflict",
        }

        first = self.client.post(
            "/api/external/v1/follow-ups",
            headers=headers,
            data={"phone": "13700137000", "content": "第一版"},
        )
        changed = self.client.post(
            "/api/external/v1/follow-ups",
            headers=headers,
            data={"phone": "13700137000", "content": "第二版"},
        )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["code"], "idempotency_conflict")
        with db_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM follow_ups WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_expired_record_is_cleaned_and_key_can_be_reused(self):
        self.issue_external_token("idempotency-token")
        headers = {
            "Authorization": "Bearer idempotency-token",
            "Idempotency-Key": "expired-key",
        }
        first = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "13600136000", "name": "过期前"},
        )
        self.assertEqual(first.status_code, 201, first.text)

        with db_conn() as conn:
            row = conn.execute(
                "SELECT expires_at FROM api_idempotency_records"
                " WHERE idempotency_key = 'expired-key'"
            ).fetchone()
            expires_at = datetime.fromisoformat(
                row["expires_at"].replace("Z", "+00:00")
            )
            remaining_days = (
                expires_at - datetime.now(timezone.utc)
            ).total_seconds() / 86400
            conn.execute(
                "UPDATE api_idempotency_records SET expires_at = ?"
                " WHERE idempotency_key = 'expired-key'",
                ("2000-01-01T00:00:00Z",),
            )

        self.assertGreater(remaining_days, 29)
        self.assertLess(remaining_days, 31)

        reused = self.client.post(
            "/api/external/v1/leads",
            headers=headers,
            json={"phone": "13500135000", "name": "过期后"},
        )
        self.assertEqual(reused.status_code, 201, reused.text)
        self.assertEqual(reused.json()["name"], "过期后")
        with db_conn() as conn:
            old_records = conn.execute(
                "SELECT COUNT(*) FROM api_idempotency_records"
                " WHERE idempotency_key = 'expired-key'"
            ).fetchone()[0]
            lead_count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        self.assertEqual(old_records, 1)
        self.assertEqual(lead_count, 2)


if __name__ == "__main__":
    unittest.main()
