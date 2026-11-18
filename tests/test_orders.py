"""订单模块测试（6 态线性流 + Q1 金额强制相等 + 禁止手动建单 + Ticket #12 列表分页排序）。"""
import unittest

from tests import _bootstrap  # noqa: F401
from tests._util import ApiTestCase, insert_customer, insert_deal, insert_order

from app.db import db_conn


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
        body = self.client.get("/api/crm/orders").json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["items"]), 2)
        only = self.client.get("/api/crm/orders", params={"status": "completed"}).json()
        self.assertEqual([r["order_no"] for r in only["items"]], ["SO-20261030-002"])

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


class OrdersListPaginationTest(ApiTestCase):
    """Ticket #12：订单列表服务端分页 + 排序（复用线索/商机页同一套校验口径）。"""

    # ---------- 分页契约 ----------
    def test_pagination_contract(self):
        c = insert_customer(name="分页客户", phone="13700000010")
        ids = [insert_order(c["id"], None, amount=float(i + 1))["id"] for i in range(25)]

        body = self.client.get("/api/crm/orders", params={"page": 2, "size": 10}).json()
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["size"], 10)
        self.assertEqual(body["total"], 25)
        self.assertEqual(len(body["items"]), 10)
        # 默认排序 id DESC：第 2 页应是倒数第 11~20 个
        self.assertEqual(body["items"][0]["id"], ids[14])

        last = self.client.get("/api/crm/orders", params={"page": 3, "size": 10}).json()
        self.assertEqual(len(last["items"]), 5)
        beyond = self.client.get("/api/crm/orders", params={"page": 4, "size": 10}).json()
        self.assertEqual(beyond["items"], [])

    def test_size_whitelist(self):
        c = insert_customer(name="白名单客户", phone="13700000011")
        for i in range(15):
            insert_order(c["id"], None, amount=float(i))
        for size in (10, 20, 50, 100, 500):
            resp = self.client.get("/api/crm/orders", params={"size": size})
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["size"], size)
        for bad in (0, 1, 15, 200, 501, -10):
            resp = self.client.get("/api/crm/orders", params={"size": bad})
            self.assertEqual(resp.status_code, 400, f"size={bad}")
            self.assertEqual(resp.json()["code"], "invalid_page_size")

    def test_page_must_be_positive(self):
        c = insert_customer(name="页码客户", phone="13700000012")
        insert_order(c["id"], None)
        for bad in (0, -1):
            resp = self.client.get("/api/crm/orders", params={"page": bad})
            self.assertEqual(resp.status_code, 400, f"page={bad}")
            self.assertEqual(resp.json()["code"], "invalid_page")
        resp = self.client.get("/api/crm/orders")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["size"], 20)  # 默认 20

    # ---------- sort / order 白名单 ----------
    def test_invalid_sort_or_order_400(self):
        c = insert_customer(name="排序客户", phone="13700000013")
        insert_order(c["id"], None)
        for url in (
            "/api/crm/orders?sort=amount;DROP TABLE orders",
            "/api/crm/orders?sort=customer_name",
            "/api/crm/orders?sort=item_count",
            "/api/crm/orders?sort=total&order=up",
            "/api/crm/orders?sort=total&order=1 desc",
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(
            self.client.get("/api/crm/orders?sort=customer_name").json()["code"],
            "invalid_sort",
        )
        self.assertEqual(
            self.client.get("/api/crm/orders?sort=total&order=up").json()["code"],
            "invalid_order",
        )

    def test_all_whitelisted_sort_keys_accepted(self):
        c = insert_customer(name="全列客户", phone="13700000014")
        insert_order(c["id"], None, amount=100.0)
        for sort in ("order_name", "customer", "product", "total",
                     "logistics", "status", "created_at"):
            for order in ("asc", "desc"):
                resp = self.client.get(
                    "/api/crm/orders", params={"sort": sort, "order": order}
                )
                self.assertEqual(resp.status_code, 200, f"{sort}/{order}")

    # ---------- 默认排序 / 稳定次键 ----------
    def test_default_order_is_id_desc(self):
        c = insert_customer(name="默认排序客户", phone="13700000015")
        ids = [insert_order(c["id"], None)["id"] for _ in range(3)]
        # 三条 created_at 压成同一值：默认排序必须有稳定次键 id DESC
        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET created_at = '2026-11-18T00:00:00Z'"
                " WHERE id IN (?, ?, ?)",
                tuple(ids),
            )
        body = self.client.get("/api/crm/orders?size=500").json()
        got = [o["id"] for o in body["items"] if o["id"] in set(ids)]
        self.assertEqual(got, list(reversed(ids)))

    def test_explicit_sort_uses_id_desc_tiebreak(self):
        c = insert_customer(name="次键客户", phone="13700000016")
        a = insert_order(c["id"], None, amount=500.0)["id"]
        b = insert_order(c["id"], None, amount=500.0)["id"]
        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET created_at = '2026-11-18T00:00:00Z'"
                " WHERE id IN (?, ?)",
                (a, b),
            )
        body = self.client.get(
            "/api/crm/orders?sort=total&order=asc&size=500"
        ).json()
        got = [o["id"] for o in body["items"] if o["id"] in {a, b}]
        self.assertEqual(got, [b, a], "金额相等时必须按 id DESC 稳定次序")

    # ---------- 排序列 ----------
    def test_sort_by_total(self):
        c = insert_customer(name="总额客户", phone="13700000017")
        a = insert_order(c["id"], None, amount=100.0)["id"]
        b = insert_order(c["id"], None, amount=300.0)["id"]
        d = insert_order(c["id"], None, amount=200.0)["id"]
        body = self.client.get(
            "/api/crm/orders?sort=total&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {a, b, d}]
        self.assertEqual(got, [a, d, b])
        body = self.client.get(
            "/api/crm/orders?sort=total&order=desc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {a, b, d}]
        self.assertEqual(got, [b, d, a])

    def test_sort_by_status(self):
        c = insert_customer(name="状态客户", phone="13700000018")
        producing = insert_order(c["id"], None, status="producing")["id"]
        completed = insert_order(c["id"], None, status="completed")["id"]
        deposit = insert_order(c["id"], None, status="deposit_paid")["id"]
        body = self.client.get(
            "/api/crm/orders?sort=status&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"]
               if x["id"] in {producing, completed, deposit}]
        # SQLite 文本序：completed < deposit_paid < producing
        self.assertEqual(got, [completed, deposit, producing])

    # ---------- JOIN 列排序 ----------
    def test_sort_by_customer_join_column(self):
        ca = insert_customer(name="张伟", phone="13700000019")
        cb = insert_customer(name="李娜", phone="13700000020")
        da = insert_order(ca["id"], None, amount=1.0)["id"]
        db_ = insert_order(cb["id"], None, amount=2.0)["id"]
        # SQLite 默认 BINARY 排序按 UTF-8 字节序：张(E5BCA0) < 李(E69D8E)
        body = self.client.get(
            "/api/crm/orders?sort=customer&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {da, db_}]
        self.assertEqual(got, [da, db_])
        body = self.client.get(
            "/api/crm/orders?sort=customer&order=desc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {da, db_}]
        self.assertEqual(got, [db_, da])

    def test_sort_by_product_name(self):
        c = insert_customer(name="产品排序客户", phone="13700000021")
        a = insert_order(c["id"], None, amount=1.0)["id"]
        b = insert_order(c["id"], None, amount=2.0)["id"]
        # 快照列不接受客户端直接写入，测试用 SQL 落库（与真实生成订单流程等价）
        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET product_name_snapshot = ? WHERE id = ?",
                ("智能天幕A", a),
            )
            conn.execute(
                "UPDATE orders SET product_name_snapshot = ? WHERE id = ?",
                ("电动天窗B", b),
            )
        body = self.client.get(
            "/api/crm/orders?sort=product&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {a, b}]
        # SQLite BINARY 按 UTF-8 字节序：智(E699BA) < 电(E794B5)
        self.assertEqual(got, [a, b])

    def test_sort_by_order_name(self):
        c = insert_customer(name="名称排序客户", phone="13700000022")
        a = insert_order(c["id"], None, amount=1.0)["id"]
        b = insert_order(c["id"], None, amount=2.0)["id"]
        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET order_name = ? WHERE id = ?", ("甲单", a)
            )
            conn.execute(
                "UPDATE orders SET order_name = ? WHERE id = ?", ("乙单", b)
            )
        body = self.client.get(
            "/api/crm/orders?sort=order_name&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {a, b}]
        # SQLite BINARY 按 UTF-8 字节序：乙(E4B999) < 甲(E794B2)
        self.assertEqual(got, [b, a])

    # ---------- 可空列 NULL 沉底 ----------
    def test_sort_nullable_nulls_last_both_directions(self):
        c = insert_customer(name="空值客户", phone="13700000023")
        named = insert_order(c["id"], None, amount=1.0)["id"]
        unnamed = insert_order(c["id"], None, amount=2.0)["id"]
        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET order_name = '有名单' WHERE id = ?", (named,)
            )

        body = self.client.get(
            "/api/crm/orders?sort=order_name&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {named, unnamed}]
        self.assertEqual(got, [named, unnamed])

        body = self.client.get(
            "/api/crm/orders?sort=order_name&order=desc&size=500"
        ).json()
        got = [x["id"] for x in body["items"] if x["id"] in {named, unnamed}]
        self.assertEqual(got, [named, unnamed])

        # 物流方式（logistics_mode）同为可空列：双向沉底
        with_logistics = insert_order(c["id"], None, amount=3.0)["id"]
        without_logistics = insert_order(c["id"], None, amount=4.0)["id"]
        with db_conn() as conn:
            conn.execute(
                "UPDATE orders SET logistics_mode = 'free'"
                " WHERE id = ?",
                (with_logistics,),
            )
        body = self.client.get(
            "/api/crm/orders?sort=logistics&order=asc&size=500"
        ).json()
        got = [x["id"] for x in body["items"]
               if x["id"] in {with_logistics, without_logistics}]
        self.assertEqual(got, [with_logistics, without_logistics])
        body = self.client.get(
            "/api/crm/orders?sort=logistics&order=desc&size=500"
        ).json()
        got = [x["id"] for x in body["items"]
               if x["id"] in {with_logistics, without_logistics}]
        self.assertEqual(got, [with_logistics, without_logistics])

    # ---------- 筛选与分页共存 ----------
    def test_filters_combine_with_pagination(self):
        c = insert_customer(name="筛选客户", phone="13700000024")
        other = insert_customer(name="筛选客户B", phone="13700000025")
        for i in range(12):
            insert_order(c["id"], None, amount=float(i))
        insert_order(other["id"], None, amount=999.0)

        body = self.client.get(
            "/api/crm/orders", params={"customer_id": c["id"], "page": 2, "size": 10}
        ).json()
        self.assertEqual(body["total"], 12)
        self.assertEqual(len(body["items"]), 2)

        body = self.client.get(
            "/api/crm/orders",
            params={"status": "completed", "customer_id": c["id"], "size": 10},
        ).json()
        self.assertEqual(body["total"], 12)

        deal = insert_deal(c["id"])
        linked = insert_order(c["id"], deal, amount=1.0)
        body = self.client.get(
            "/api/crm/orders", params={"deal_id": deal["id"], "size": 500}
        ).json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["id"], linked["id"])


if __name__ == "__main__":
    unittest.main()
