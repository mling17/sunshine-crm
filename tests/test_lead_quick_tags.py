"""详情页线索标签：多选后一次保存，只写一条汇总履历。"""

from __future__ import annotations

from tests import _bootstrap  # noqa: F401
from tests._util import ApiTestCase


class LeadQuickTagsTest(ApiTestCase):
    def _lead(self, *, name: str = "张伟", phone: str = "13800138000") -> dict:
        resp = self.client.post(
            "/api/crm/leads",
            json={"name": name, "phone": phone, "source": "wechat"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def _change_entries(self, lead_id: int) -> list[dict]:
        history = self.client.get(
            "/api/crm/follow-ups",
            params={
                "object_type": "lead",
                "object_id": lead_id,
                "include_system": "true",
            },
        ).json()
        return [item for item in history if item["kind"] == "change"]

    def test_multiple_tags_save_in_one_change_and_removal_keeps_dictionary(self):
        lead = self._lead()

        saved = self.client.put(
            f"/api/crm/leads/{lead['id']}/tags",
            json={"tags": ["  重点客户  ", "待量尺"]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        tags = saved.json()
        self.assertEqual([tag["name"] for tag in tags], ["重点客户", "待量尺"])
        self.assertTrue(all(tag["id"] > 0 for tag in tags))

        detail = self.client.get(f"/api/crm/leads/{lead['id']}").json()
        self.assertEqual(detail["tags"], ["重点客户", "待量尺"])
        self.assertIn("重点客户", self.client.get("/api/crm/tags").json())

        changes = self._change_entries(lead["id"])
        self.assertEqual(len(changes), 1, "多选保存只能生成一条变更履历")
        self.assertEqual(
            changes[0]["content"],
            "更新线索标签：添加「重点客户、待量尺」",
        )

        mixed = self.client.put(
            f"/api/crm/leads/{lead['id']}/tags",
            json={"tags": ["重点客户", "门店客户"]},
        )
        self.assertEqual(mixed.status_code, 200, mixed.text)
        changes = self._change_entries(lead["id"])
        self.assertEqual(len(changes), 2)
        self.assertEqual(
            changes[0]["content"],
            "更新线索标签：添加「门店客户」；删除「待量尺」",
        )

        removed = self.client.put(
            f"/api/crm/leads/{lead['id']}/tags",
            json={"tags": []},
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json(), [])
        self.assertEqual(
            self.client.get(f"/api/crm/leads/{lead['id']}").json()["tags"],
            [],
        )
        self.assertIn(
            "重点客户",
            self.client.get("/api/crm/tags").json(),
            "移除线索标签不能删除全局共用标签",
        )

    def test_same_tag_is_shared_and_unchanged_selection_adds_no_history(self):
        first = self._lead(name="客户A", phone="13800138001")
        second = self._lead(name="客户B", phone="13800138002")

        first_tags = self.client.put(
            f"/api/crm/leads/{first['id']}/tags",
            json={"tags": ["待量尺"]},
        ).json()
        second_tags = self.client.put(
            f"/api/crm/leads/{second['id']}/tags",
            json={"tags": ["待量尺"]},
        ).json()
        self.assertEqual(first_tags[0]["id"], second_tags[0]["id"])

        repeated = self.client.put(
            f"/api/crm/leads/{first['id']}/tags",
            json={"tags": ["待量尺"]},
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(len(repeated.json()), 1)
        self.assertEqual(len(self._change_entries(first["id"])), 1)

        with self.db_conn() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM lead_tags").fetchone()["n"],
                2,
            )

    def test_bulk_tag_save_validates_blank_limit_and_terminal_state(self):
        lead = self._lead()
        blank = self.client.put(
            f"/api/crm/leads/{lead['id']}/tags",
            json={"tags": ["   "]},
        )
        self.assertEqual(blank.status_code, 400, blank.text)
        self.assertEqual(blank.json()["code"], "lead_tag_required")

        overflow = self.client.put(
            f"/api/crm/leads/{lead['id']}/tags",
            json={"tags": [f"标签{index:02d}" for index in range(21)]},
        )
        self.assertEqual(overflow.status_code, 400, overflow.text)

        other = self._lead(name="失效客户", phone="13800138003")
        self.client.post(
            f"/api/crm/leads/{other['id']}/invalidate",
            json={"invalid_reason": "no_intent"},
        )
        closed = self.client.put(
            f"/api/crm/leads/{other['id']}/tags",
            json={"tags": ["重点客户"]},
        )
        self.assertEqual(closed.status_code, 409, closed.text)
        self.assertEqual(closed.json()["code"], "lead_closed")

