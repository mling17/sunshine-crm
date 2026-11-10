"""订单模块测试（6 态线性流 + Q1 金额强制相等 + 禁止手动建单）。"""
import unittest

from tests import _bootstrap  # noqa: F401
from tests._util import ApiTestCase, insert_customer, insert_deal, insert_order


class OrdersTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.customer = insert_customer(name="订单客户", phone="13700000001")
        self.deal = insert_deal(self.customer["id"], stage="won", amount=1000.0)
        self.order = insert_order(self.customer["id"], self.deal, amount=1000.0,
                                  status="pending_payment")

    def transition(self, to_status, **kwargs):
        body = {"to_status": to_status}
        body.update(kwargs)
        return self.client.post(f"/api/crm/orders/{self.order['id']}/transition", json=body)

    # ---------- 建单限制 ----------
    def test_create_order_forbidden(self):
        resp = self.client.post("/api/crm/orders", json={
            "customer_id": self.customer["id"], "deal_id": self.deal["id"],
            "amount": 1000.0, "status": "pending_payment",
        })
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(resp.json()["code"], "order_create_forbidden")

    # ---------- 读 ----------
    def test_get_order(self):
        resp = self.client.get(f"/api/crm/orders/{self.order['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["id"], self.order["id"])
        self.assertEqual(data["order_no"], "SO-20261030-001")
        self.assertEqual(data["status"], "pending_payment")
        self.assertIsInstance(data["status_log"], list)

    def test_get_missing_order_404(self):
        self.assertEqual(self.client.get("/api/crm/orders/9999").status_code, 404)

    def test_list_orders(self):
        insert_order(self.customer["id"], None, order_no="SO-20261030-002",
                     amount=500.0, status="completed")
        rows = self.client.get("/api/crm/orders").json()
        self.assertEqual(len(rows), 2)
        only = self.client.get("/api/crm/orders", params={"status": "completed"}).json()
        self.assertEqual([r["order_no"] for r in only], ["SO-20261030-002"])

    def test_order_status_dictionary_excludes_shipped(self):
        items = self.client.get("/api/crm/dicts/order_status").json()["items"]
        keys = [item["key"] for item in items]
        self.assertNotIn("shipped", keys)
        self.assertEqual(len(keys), 7)
        self.assertTrue(
            {
                "pending_confirmation", "pending_payment", "deposit_paid",
                "producing", "balance_paid", "ready_to_ship", "completed",
            }.issubset(set(keys))
        )

    # ---------- 状态机 ----------
    def test_invalid_transition(self):
        # 越级：待支付 → 生产中
        resp = self.transition("producing")
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "invalid_transition")

    def test_q1_deposit_exceeds_amount(self):
        resp = self.transition("deposit_paid", deposit=2000.0)
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "invalid_deposit")

    def test_q1_balance_must_equal_remaining(self):
        r = self.transition("deposit_paid", deposit=400.0)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.transition("producing")
        self.assertEqual(r.status_code, 200, r.text)
        # 尾款 != 总额 - 已收押金（600）→ 拒绝
        bad = self.transition("balance_paid", balance=500.0)
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "amount_mismatch")
        # 精确相等 → 通过
        ok = self.transition("balance_paid", balance=600.0)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["order"]["status"], "balance_paid")

    def test_full_flow_self_delivery(self):
        self.assertEqual(self.transition("deposit_paid", deposit=1000.0).status_code, 200)
        self.assertEqual(self.transition("producing").status_code, 200)
        self.assertEqual(self.transition("balance_paid", balance=0.0).status_code, 200)
        self.assertEqual(self.transition("ready_to_ship", logistics_mode="self").status_code, 200)
        removed = self.transition("shipped")
        self.assertEqual(removed.status_code, 400, removed.text)
        self.assertEqual(removed.json()["code"], "invalid_transition")
        done = self.transition("completed", received_at="2026-10-31T10:00:00")
        self.assertEqual(done.status_code, 200, done.text)
        order = self.client.get(f"/api/crm/orders/{self.order['id']}").json()
        self.assertEqual(order["status"], "completed")
        self.assertEqual(order["tracking_number"], "无")

    def test_carrier_mode_requires_tracking(self):
        self.transition("deposit_paid", deposit=1000.0)
        self.transition("producing")
        self.transition("balance_paid", balance=0.0)
        noscreen = self.transition("ready_to_ship", logistics_mode="agent", carrier_id=1)
        self.assertEqual(noscreen.status_code, 400, noscreen.text)

    def test_carrier_delete_protection(self):
        c = self.client.post("/api/crm/carriers", json={"name": "顺丰", "code": "SF"})
        self.assertEqual(c.status_code, 200, c.text)
        cid = c.json()["id"]
        with self.db_conn() as conn:
            conn.execute("UPDATE orders SET carrier_id = ? WHERE id = ?", (cid, self.order["id"]))
        resp = self.client.delete(f"/api/crm/carriers/{cid}")
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "carrier_in_use")


if __name__ == "__main__":
    unittest.main()
