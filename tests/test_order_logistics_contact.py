"""订单物流联络人快照与订单自有信息编辑回归测试。"""

from __future__ import annotations

import unittest

from tests._util import ApiTestCase


class OrderLogisticsContactTest(ApiTestCase):
    def _deal(self, amount: float = 10000.0) -> tuple[dict, dict]:
        customer = self.create_customer(name="物流联系人客户", phone="13982000001")
        deal = self.create_deal(customer["id"], amount=amount, drive_type="manual")
        promoted = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"}
        )
        self.assertEqual(promoted.status_code, 200, promoted.text)
        return customer, deal

    def _create_agent_order(self, carrier: dict, deal: dict) -> dict:
        response = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "deposit": 3000,
                "logistics_mode": "agent",
                "carrier_id": carrier["id"],
                "carrier_contact_id": carrier["contacts"][0]["id"],
                "logistics_fee": 300,
                "receiver_name": "张三",
                "receiver_phone": "13982000002",
                "receiver_address": "上海市浦东新区测试路 1 号",
                "note": "初始备注",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["order"]

    def test_create_order_requires_and_snapshots_carrier_contact(self):
        _, deal = self._deal()
        carrier = self.create_carrier(
            name="联系人快照物流",
            contacts=[{"name": "王经理", "phone": "13982000003", "tags": ["大件"]}],
        )
        missing = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "deposit": 3000,
                "logistics_mode": "agent",
                "carrier_id": carrier["id"],
                "receiver_name": "张三",
                "receiver_phone": "13982000002",
                "receiver_address": "上海市浦东新区测试路 1 号",
            },
        )
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertEqual(missing.json()["code"], "carrier_contact_required")

        response = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "deposit": 3000,
                "logistics_mode": "agent",
                "carrier_id": carrier["id"],
                "carrier_contact_id": carrier["contacts"][0]["id"],
                "logistics_fee": 300,
                "receiver_name": "张三",
                "receiver_phone": "13982000002",
                "receiver_address": "上海市浦东新区测试路 1 号",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        order = response.json()["order"]
        self.assertEqual(order["carrier_contact_id"], carrier["contacts"][0]["id"])
        self.assertEqual(order["carrier_contact_name"], "王经理")
        self.assertEqual(order["carrier_contact_phone"], "13982000003")

        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["carrier_contact_name"], "王经理")
        self.assertEqual(detail["carrier_contact_phone"], "13982000003")
        self.assertEqual(detail["product_total"], 10000.0)
        self.assertEqual(detail["amount"], 10300.0)

    def test_contact_must_belong_to_selected_carrier(self):
        _, deal = self._deal()
        first = self.create_carrier(name="物流公司甲")
        second = self.create_carrier(name="物流公司乙")
        response = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "deposit": 3000,
                "logistics_mode": "agent",
                "carrier_id": first["id"],
                "carrier_contact_id": second["contacts"][0]["id"],
                "receiver_name": "张三",
                "receiver_phone": "13982000002",
                "receiver_address": "上海市浦东新区测试路 1 号",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "carrier_contact_not_found")

    def test_edit_order_changes_logistics_and_delivery_after_completion(self):
        _, deal = self._deal()
        first = self.create_carrier(name="发货物流甲")
        second = self.create_carrier(
            name="发货物流乙",
            contacts=[{"name": "李经理", "phone": "13982000004", "tags": []}],
        )
        order = self._create_agent_order(first, deal)
        with self.db_conn() as conn:
            conn.execute(
                "UPDATE orders SET status = 'completed' WHERE id = ?", (order["id"],)
            )

        updated = self.client.put(
            f"/api/crm/orders/{order['id']}",
            json={
                "logistics_mode": "free",
                "carrier_id": second["id"],
                "carrier_contact_id": second["contacts"][0]["id"],
                "logistics_fee": 500,
                "tracking_number": "EDIT-CONTACT-001",
                "receiver_name": "李收货",
                "receiver_phone": "13982000005",
                "receiver_address": "上海市徐汇区新地址 2 号",
                "note": "客户要求周六送货",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        data = updated.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["carrier_id"], second["id"])
        self.assertEqual(data["carrier_contact_name"], "李经理")
        self.assertEqual(data["carrier_contact_phone"], "13982000004")
        self.assertEqual(data["logistics_fee"], 500.0)
        self.assertEqual(data["tracking_number"], "EDIT-CONTACT-001")
        self.assertEqual(data["receiver_name"], "李收货")
        self.assertEqual(data["note"], "客户要求周六送货")
        self.assertEqual(data["product_total"], 10000.0)
        self.assertEqual(data["product_payable"], 10000.0)
        self.assertEqual(data["amount"], 10500.0)

        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["balance_amount"], 7500.0)
        self.assertEqual(detail["product_name_snapshot"], order["product_name_snapshot"])
        self.assertEqual(detail["product_config_snapshot"], order["product_config_snapshot"])
        self.assertEqual(detail["status_log"][-1]["event_type"], "address")
        self.assertIn("修改订单", detail["status_log"][-1]["note"])


if __name__ == "__main__":
    unittest.main()
