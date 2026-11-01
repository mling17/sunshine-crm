"""多产品商机、整单优惠、独立运费和客户确认的回归测试。"""

from __future__ import annotations

import unittest

from tests._util import ApiTestCase


class MultiProductOrderTest(ApiTestCase):
    def _products(self) -> list[dict]:
        resp = self.client.get("/api/crm/products")
        self.assertEqual(resp.status_code, 200, resp.text)
        products = resp.json()
        self.assertGreaterEqual(len(products), 2)
        return products

    def _deal_with_two_lines(self) -> tuple[dict, dict, list[dict]]:
        products = self._products()
        customer = self.create_customer(name="多产品客户", phone="13911112222")
        deal = self.create_deal(
            customer["id"],
            product_id=products[0]["id"],
            product_type=products[0]["category"],
            model=products[0]["code"],
            spec="1200*2400",
            amount=5000.0,
            drive_type=products[0].get("drive_type") or "manual",
        )
        second = self.client.post(
            f"/api/crm/deals/{deal['id']}/items",
            json={
                "product_id": products[1]["id"],
                "quantity": 2,
                "spec": "1000*1800",
                "production_spec": "框 980*1780；扇 960*1760",
                "unit_price": 6000.0,
                "note": "第二条产品",
            },
        )
        self.assertEqual(second.status_code, 200, second.text)
        detail = self.client.get(f"/api/crm/deals/{deal['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        data = detail.json()
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["amount"], 17000.0)
        return deal, customer, data["items"]

    def test_multi_product_order_keeps_discount_and_freight_separate(self):
        deal, customer, items = self._deal_with_two_lines()
        self.assertEqual(items[1]["amount"], 12000.0)

        promoted = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"}
        )
        self.assertEqual(promoted.status_code, 200, promoted.text)

        carrier = self.create_carrier(name="多产品测试物流")
        created = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "discount_amount": 1000.0,
                "discount_reason": "微信协商整单优惠",
                "deposit": 3000.0,
                "logistics_mode": "agent",
                "carrier_id": carrier["id"],
                "logistics_fee": 600.0,
                "receiver_name": "多产品客户",
                "receiver_phone": "13911112222",
                "receiver_address": "上海市测试路 1 号",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        order = body["order"]
        self.assertEqual(order["status"], "pending_confirmation")
        self.assertEqual(order["product_total"], 17000.0)
        self.assertEqual(order["discount_amount"], 1000.0)
        self.assertEqual(order["product_payable"], 16000.0)
        self.assertEqual(order["logistics_fee"], 600.0)
        self.assertEqual(order["amount"], 16600.0)
        self.assertEqual(order["deposit_amount"], 3000.0)
        self.assertEqual(order["balance_amount"], 13600.0)
        self.assertEqual(body["deal"]["stage"], "confirm")

        detail = self.client.get(f"/api/crm/orders/{order['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        data = detail.json()
        self.assertEqual(data["item_count"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][1]["production_spec"], "框 980*1780；扇 960*1760")
        self.assertEqual(data["product_total"], 17000.0)
        self.assertEqual(data["freight_amount"], 600.0)
        self.assertIsNone(data["customer_confirmed_at"])
        status_labels = {
            item["key"]: item["label"]
            for item in self.client.get("/api/crm/dicts/order_status").json()["items"]
        }
        self.assertIn(
            status_labels["pending_confirmation"],
            [entry["to_status_label"] for entry in data["status_log"]],
        )

        confirmed = self.client.post(
            f"/api/crm/orders/{order['id']}/confirm",
            data={"note": "客户已微信确认下单表，并确认优惠 1000 元、运费 600 元"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        confirmed_data = confirmed.json()
        self.assertEqual(confirmed_data["status"], "pending_payment")
        self.assertTrue(confirmed_data["customer_confirmed_at"])
        self.assertIn("微信确认", confirmed_data["customer_confirmation_note"])
        self.assertIn(
            status_labels["pending_payment"],
            [entry["to_status_label"] for entry in confirmed_data["status_log"]],
        )

        deal_after = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(deal_after["stage"], "won")
        self.assertTrue(deal_after["closed_at"])
        self.assertEqual(deal_after["order_id"], order["id"])

    def test_discount_cannot_reduce_freight_or_exceed_products(self):
        deal, _, _ = self._deal_with_two_lines()
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        resp = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "discount_amount": 17001.0,
                "deposit": 1.0,
                "logistics_mode": "self",
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "invalid_discount")

    def test_deal_manual_stage_cannot_skip_customer_confirmation(self):
        customer = self.create_customer(name="阶段客户", phone="13933334444")
        deal = self.create_deal(customer["id"], amount=1000.0)
        resp = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"stage": "won"}
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "stage_via_customer_confirmation")

    def test_last_product_line_cannot_be_deleted(self):
        customer = self.create_customer(name="单产品客户", phone="13955556666")
        deal = self.create_deal(customer["id"], amount=1000.0)
        detail = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        item_id = detail["items"][0]["id"]
        resp = self.client.delete(f"/api/crm/deals/{deal['id']}/items/{item_id}")
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "last_deal_item")


if __name__ == "__main__":
    unittest.main()
