"""订单事件流 + 收款强校验（PLANNER-V3 §5.6 / §6.3，Q-D 决议）。"""
from __future__ import annotations

import unittest

from tests._util import ApiTestCase


class OrderTimelineTest(ApiTestCase):
    def _order(self, amount: float = 10000.0, deposit: float = 3000.0):
        c = self.create_customer(name="王测试")
        deal = self.create_deal(c["id"], amount=amount, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "won"})
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
        return resp.json()["order"]

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
        self.assertEqual([t["type"] for t in detail["timeline"]], ["order"])
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


if __name__ == "__main__":
    unittest.main()