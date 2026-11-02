"""完成订单的后续处理边界：跟进转售后、标签只读。"""
from __future__ import annotations

import unittest

from tests._util import ApiTestCase, insert_customer, insert_order

from app.db import db_conn


class OrderCompletionGuardsTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.customer = insert_customer(name="完成订单客户")

    def test_completed_order_cannot_be_followed_up(self):
        order = insert_order(customer_id=self.customer["id"], status="completed")
        resp = self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "order",
                "object_id": str(order["id"]),
                "content": "完成后继续联系客户",
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "order_completed_use_aftersale")

    def test_processing_order_still_allows_follow_up(self):
        order = insert_order(customer_id=self.customer["id"], status="producing")
        resp = self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "order",
                "object_id": str(order["id"]),
                "content": "跟进生产进度",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_completed_order_locks_deal_tags(self):
        order = insert_order(customer_id=self.customer["id"], status="producing")
        deal_id = int(order["deal_id"])

        added = self.client.post(
            f"/api/crm/deals/{deal_id}/tags", json={"name": "安装完成"}
        )
        self.assertEqual(added.status_code, 200, added.text)
        manual_tag = next(tag for tag in added.json() if tag["source"] == "manual")

        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET status = 'completed' WHERE id = ?",
                (order["id"],),
            )

        create = self.client.post(
            f"/api/crm/deals/{deal_id}/tags", json={"name": "完成后新增"}
        )
        self.assertEqual(create.status_code, 409, create.text)
        self.assertEqual(create.json()["code"], "deal_tags_locked")

        delete = self.client.delete(
            f"/api/crm/deals/{deal_id}/tags/{manual_tag['id']}"
        )
        self.assertEqual(delete.status_code, 409, delete.text)
        self.assertEqual(delete.json()["code"], "deal_tags_locked")


if __name__ == "__main__":
    unittest.main()
