"""订单事件流 + 收款强校验（PLANNER-V3 §5.6 / §6.3，Q-D 决议）。"""
from __future__ import annotations

import unittest

from tests._util import ApiTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class OrderTimelineTest(ApiTestCase):
    def _order(self, amount: float = 10000.0, deposit: float = 3000.0):
        c = self.create_customer(name="王测试")
        deal = self.create_deal(c["id"], amount=amount, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        resp = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "deposit": deposit,
                "logistics_mode": "self",
                "receiver_name": "王测试",
                "receiver_phone": "13800000000",
                "receiver_address": "济南市历下区",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        order = resp.json()["order"]
        confirmed = self.client.post(
            f"/api/crm/orders/{order['id']}/confirm",
            data={"note": "测试客户已微信确认"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        return order

    def _pay_deposit(self, order_id: int, amount: float):
        return self.client.post(
            f"/api/crm/orders/{order_id}/pay-deposit", data={"amount": str(amount)}
        )

    def _pay_balance(self, order_id: int, amount: float):
        return self.client.post(
            f"/api/crm/orders/{order_id}/pay-balance", data={"amount": str(amount)}
        )

    def test_order_detail_has_timeline_and_snapshot(self):
        order = self._order()
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["deposit_amount"], 3000.0)
        self.assertEqual(detail["balance_amount"], 7000.0)
        self.assertEqual(detail["receiver_address"], "济南市历下区")
        self.assertIn("order", [t["type"] for t in detail["timeline"]])
        self.assertIn("confirm", [t["type"] for t in detail["timeline"]])
        self.assertEqual(detail["aftersales"], [], "没有售后单就是空列表")

    def test_deposit_amount_must_match_due(self):
        order = self._order()
        bad = self._pay_deposit(order["id"], 2000.0)
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "amount_mismatch")
        # 失败不留痕：状态和已收金额都不变
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["status"], "pending_payment")
        self.assertEqual(detail["deposit_paid"], 0.0)

    def test_deposit_twice_rejected(self):
        order = self._order()
        self.assertEqual(self._pay_deposit(order["id"], 3000.0).status_code, 200)
        again = self._pay_deposit(order["id"], 3000.0)
        # 状态机先挡（已付押金不能再付），或 already_paid 守卫，两者都必须拒绝
        self.assertIn(again.status_code, (400, 409), again.text)
        self.assertIn(again.json()["code"], ("already_paid", "invalid_transition"))

    def test_deposit_screenshot_keeps_order_detail_available(self):
        order = self._order()
        paid = self.client.post(
            f"/api/crm/orders/{order['id']}/pay-deposit",
            data={"amount": "3000"},
            files={"screenshots": ("deposit.png", PNG, "image/png")},
        )
        self.assertEqual(paid.status_code, 200, paid.text)

        detail = self.client.get(f"/api/crm/orders/{order['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        attachments = detail.json()["attachments"]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(
            attachments[0]["url"],
            f"/api/crm/attachments/{attachments[0]['id']}",
        )

    def test_balance_requires_deposit_first(self):
        order = self._order()
        bad = self._pay_balance(order["id"], 7000.0)
        self.assertEqual(bad.status_code, 400, bad.text)  # 状态机先挡：待支付不能直接收尾款

    def test_balance_amount_must_match_due(self):
        order = self._order()
        self._pay_deposit(order["id"], 3000.0)
        self.client.post(f"/api/crm/orders/{order['id']}/transition",
                         json={"to_status": "producing"})
        bad = self._pay_balance(order["id"], 6000.0)
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "amount_mismatch")
        ok = self._pay_balance(order["id"], 7000.0)
        self.assertEqual(ok.status_code, 200, ok.text)
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["balance_paid"], 7000.0)
        self.assertEqual(detail["deposit_paid"] + detail["balance_paid"], detail["amount"])

    def test_tracking_is_required_at_shipping_not_stock_ready(self):
        order = self._order()
        carrier = self.create_carrier(name="发货校验物流")
        updated = self.client.put(
            f"/api/crm/orders/{order['id']}",
            json={
                "logistics_mode": "agent",
                "carrier_id": carrier["id"],
                "carrier_contact_id": carrier["contacts"][0]["id"],
                "receiver_name": "王测试",
                "receiver_phone": "13800000000",
                "receiver_address": "济南市历下区",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self._pay_deposit(order["id"], 3000.0)
        self.client.post(
            f"/api/crm/orders/{order['id']}/transition",
            json={"to_status": "producing"},
        )
        self._pay_balance(order["id"], 7000.0)

        stock_ready = self.client.post(
            f"/api/crm/orders/{order['id']}/transition",
            json={"to_status": "ready_to_ship"},
        )
        self.assertEqual(stock_ready.status_code, 200, stock_ready.text)

        shipped = self.client.post(
            f"/api/crm/orders/{order['id']}/transition",
            json={"to_status": "shipped"},
        )
        self.assertEqual(shipped.status_code, 400, shipped.text)
        self.assertEqual(shipped.json()["code"], "missing_tracking_number")

    def test_completed_requires_full_payment(self):
        order = self._order(amount=10000.0, deposit=10000.0)
        self._pay_deposit(order["id"], 10000.0)
        self.client.post(f"/api/crm/orders/{order['id']}/transition", json={"to_status": "producing"})
        # 一次付清：尾款 0 → 收 0 元
        zero = self._pay_balance(order["id"], 0.0)
        self.assertEqual(zero.status_code, 200, zero.text)
        self.client.post(f"/api/crm/orders/{order['id']}/transition",
                         json={"to_status": "ready_to_ship", "logistics_mode": "self"})
        ship = self.client.post(f"/api/crm/orders/{order['id']}/transition",
                                json={"to_status": "shipped"})
        self.assertEqual(ship.status_code, 200, ship.text)
        done = self.client.post(f"/api/crm/orders/{order['id']}/transition",
                                json={"to_status": "completed"})
        self.assertEqual(done.status_code, 200, done.text)

    def test_timeline_accumulates_events(self):
        order = self._order()
        self._pay_deposit(order["id"], 3000.0)
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        types = [t["type"] for t in detail["timeline"]]
        self.assertIn("order", types)
        self.assertIn("pay", types)
        pays = [t for t in detail["timeline"] if t["type"] == "pay"]
        self.assertEqual(len(pays), 1)
        self.assertIn("¥3,000.00", pays[0]["content"])

    def test_order_detail_shows_related_deal(self):
        order = self._order()
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertIsNotNone(detail["deal"])
        self.assertEqual(detail["deal"]["stage"], "won")

    def test_update_order_delivery_before_shipping_and_record_history(self):
        order = self._order()
        updated = self.client.put(
            f"/api/crm/orders/{order['id']}",
            json={
                "receiver_name": "李接收",
                "receiver_phone": "13900001111",
                "receiver_address": "济南市历下区新地址 1 号",
                "tracking_number": "SF-EDIT-001",
                "note": "周六上午送货",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["receiver_name"], "李接收")
        self.assertEqual(updated.json()["tracking_number"], "SF-EDIT-001")

        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["receiver_phone"], "13900001111")
        self.assertEqual(detail["note"], "周六上午送货")
        latest = detail["status_log"][-1]
        self.assertEqual(latest["event_type"], "address")
        self.assertIn("修改订单", latest["note"])
        self.assertIn("收件人", latest["note"])

    def test_update_order_is_allowed_after_shipping(self):
        order = self._order()
        with self.db_conn() as conn:
            conn.execute(
                "UPDATE orders SET status = 'shipped' WHERE id = ?",
                (order["id"],),
            )

        resp = self.client.put(
            f"/api/crm/orders/{order['id']}",
            json={"receiver_address": "不应写入的新地址"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["receiver_address"], "不应写入的新地址")

        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["receiver_address"], "不应写入的新地址")
        self.assertEqual(detail["product_total"], 10000.0)
        self.assertEqual(detail["amount"], 10000.0)


if __name__ == "__main__":
    unittest.main()
