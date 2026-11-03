"""跟进常用短语：五类业务对象独立维护、软删除与鉴权。"""

from __future__ import annotations

import unittest

from tests import _bootstrap  # noqa: F401  # 必须先设定临时库

from app.db import db_conn
from tests._util import ApiTestCase, open_client


class FollowupPhrasesTest(ApiTestCase):
    def create_phrase(self, object_type: str, content: str):
        return self.client.post(
            "/api/crm/follow-up-phrases",
            json={"object_type": object_type, "content": content},
        )

    def list_phrases(self, object_type: str) -> list[dict]:
        response = self.client.get(
            "/api/crm/follow-up-phrases",
            params={"object_type": object_type},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_each_business_object_has_an_independent_phrase_set(self):
        object_types = ("lead", "customer", "deal", "order", "aftersale")
        for index, object_type in enumerate(object_types, start=1):
            response = self.create_phrase(
                object_type,
                f"独立集合-{self._testMethodName}-{index}",
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["object_type"], object_type)

        for index, object_type in enumerate(object_types, start=1):
            items = self.list_phrases(object_type)
            self.assertTrue(all(item["object_type"] == object_type for item in items))
            self.assertIn(
                f"独立集合-{self._testMethodName}-{index}",
                [item["content"] for item in items],
            )

        shared = f"跨集合同文-{self._testMethodName}"
        for object_type in ("lead", "customer"):
            response = self.create_phrase(object_type, shared)
            self.assertEqual(response.status_code, 201, response.text)

    def test_duplicate_phrase_is_rejected_within_same_object_type(self):
        content = "本周内发送报价"
        first = self.create_phrase("deal", content)
        self.assertEqual(first.status_code, 201, first.text)

        duplicate = self.create_phrase("deal", f"  {content}  ")
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertIn("已经存在", duplicate.json()["detail"])

    def test_delete_is_soft_and_phrase_can_be_recreated(self):
        created = self.create_phrase("aftersale", "维修师傅已上门")
        self.assertEqual(created.status_code, 201, created.text)
        phrase_id = created.json()["id"]

        deleted = self.client.delete(f"/api/crm/follow-up-phrases/{phrase_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json(), {"ok": True, "id": phrase_id})
        self.assertNotIn(phrase_id, [item["id"] for item in self.list_phrases("aftersale")])

        with db_conn() as conn:
            row = conn.execute(
                "SELECT is_delete, update_time FROM follow_up_phrases WHERE id = ?",
                (phrase_id,),
            ).fetchone()
        self.assertEqual(row["is_delete"], 1)
        self.assertTrue(row["update_time"])

        recreated = self.create_phrase("aftersale", "维修师傅已上门")
        self.assertEqual(recreated.status_code, 201, recreated.text)
        self.assertEqual(
            self.client.delete(f"/api/crm/follow-up-phrases/{phrase_id}").status_code,
            404,
        )

    def test_phrase_validation(self):
        blank = self.create_phrase("customer", "   ")
        self.assertEqual(blank.status_code, 400, blank.text)

        too_long = self.create_phrase("customer", "客" * 201)
        self.assertEqual(too_long.status_code, 400, too_long.text)

        invalid_type = self.create_phrase("product", "不支持的短语")
        self.assertEqual(invalid_type.status_code, 400, invalid_type.text)

        invalid_filter = self.client.get(
            "/api/crm/follow-up-phrases",
            params={"object_type": "product"},
        )
        self.assertEqual(invalid_filter.status_code, 400, invalid_filter.text)

    def test_phrase_crud_requires_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(
            anon.get(
                "/api/crm/follow-up-phrases",
                params={"object_type": "lead"},
            ).status_code,
            401,
        )
        self.assertEqual(
            anon.post(
                "/api/crm/follow-up-phrases",
                json={"object_type": "lead", "content": "匿名不能添加"},
            ).status_code,
            401,
        )
        self.assertEqual(
            anon.delete("/api/crm/follow-up-phrases/1").status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
