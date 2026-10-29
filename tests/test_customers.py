"""T3：客户档案 CRUD + 搜索 + 分页 + 详情 + 级联删除。"""

from __future__ import annotations

import unittest

from tests._util import ApiTestCase, insert_deal, insert_follow_up, open_client

from app.db import db_conn


class CustomersTest(ApiTestCase):
    # ---------- 建 + 列表 ----------
    def test_create_and_list(self):
        a = self.create_customer(
            name="张伟",
            phone="13800000001",
            wechat="zw001",
            location="阳光小区",
            house_note="三居，主卧朝南",
        )
        self.create_customer(name="李娜", phone="13900000002", location="翡翠湾")

        self.assertIsInstance(a["id"], int)
        self.assertEqual(a["name"], "张伟")
        self.assertEqual(a["phone"], "13800000001")
        self.assertEqual(a["wechat"], "zw001")
        self.assertEqual(a["location"], "阳光小区")
        self.assertEqual(a["house_note"], "三居，主卧朝南")
        self.assertTrue(a["created_at"])
        self.assertTrue(a["updated_at"])
        # 新客户默认无商机（标签口径在 T3b 的 tests/test_tags.py 覆盖）
        self.assertEqual(a["deals_total"], 0)
        self.assertEqual(a["total_closed_amount"], 0)

        body = self.client.get("/api/crm/customers").json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["page"], 1)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual({c["name"] for c in body["items"]}, {"张伟", "李娜"})

    # ---------- 搜索：name / phone / location ----------
    def test_search_by_name_phone_and_location(self):
        self.create_customer(name="张伟", phone="13800000001", location="阳光小区")
        self.create_customer(name="李娜", phone="13900000002", location="翡翠湾")

        for term, expected in [("张", "张伟"), ("13900000002", "李娜"), ("翡翠", "李娜")]:
            body = self.client.get("/api/crm/customers", params={"search": term}).json()
            self.assertEqual(body["total"], 1, term)
            self.assertEqual(body["items"][0]["name"], expected, term)

        body = self.client.get("/api/crm/customers", params={"search": "查无此人"}).json()
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["items"], [])

    def test_search_wildcards_are_escaped(self):
        """``%`` / ``_`` 按字面匹配，不能让用户输入变成通配符。"""
        self.create_customer(name="100%满意")
        self.create_customer(name="张三")
        body = self.client.get("/api/crm/customers", params={"search": "0%满"}).json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["name"], "100%满意")
        body = self.client.get("/api/crm/customers", params={"search": "%"}).json()
        self.assertEqual(body["total"], 1)

    # ---------- 分页 ----------
    def test_pagination(self):
        for i in range(5):
            self.create_customer(name=f"客户{i}")

        page1 = self.client.get("/api/crm/customers", params={"page": 1, "size": 2}).json()
        page2 = self.client.get("/api/crm/customers", params={"page": 2, "size": 2}).json()
        page3 = self.client.get("/api/crm/customers", params={"page": 3, "size": 2}).json()
        over = self.client.get("/api/crm/customers", params={"page": 9, "size": 2}).json()

        self.assertEqual((page1["total"], page2["total"], page3["total"]), (5, 5, 5))
        self.assertEqual((len(page1["items"]), len(page2["items"]), len(page3["items"])), (2, 2, 1))
        self.assertEqual(over["items"], [], "页码越界返回空 items，不报错")
        ids = [c["id"] for c in page1["items"] + page2["items"] + page3["items"]]
        self.assertEqual(len(set(ids)), 5, "分页不重不漏")

    # ---------- 改 ----------
    def test_update_fields(self):
        c = self.create_customer(name="张伟", location="旧地址")

        resp = self.client.put(
            f"/api/crm/customers/{c['id']}",
            json={"location": "新地址", "phone": "13800000001"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        updated = resp.json()
        self.assertEqual(updated["location"], "新地址")
        self.assertEqual(updated["phone"], "13800000001")
        # 没传的字段不许被清空
        self.assertEqual(updated["name"], "张伟")
        self.assertEqual(updated["id"], c["id"])

        detail = self.client.get(f"/api/crm/customers/{c['id']}").json()
        self.assertEqual(detail["location"], "新地址")

    # ---------- 详情 ----------
    def test_detail_contains_deals_and_recent_follow_ups(self):
        c = self.create_customer(name="张伟")
        deal_id = insert_deal(c["id"], amount=8800.0)
        insert_follow_up(c["id"], content="首次上门量尺", deal_id=deal_id, next_date="2026-10-30")
        insert_follow_up(c["id"], content="微信聊了一次")

        resp = self.client.get(f"/api/crm/customers/{c['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        detail = resp.json()

        self.assertEqual(detail["id"], c["id"])
        self.assertEqual(detail["name"], "张伟")
        self.assertEqual(len(detail["deals"]), 1)
        self.assertEqual(detail["deals"][0]["id"], deal_id)
        self.assertEqual(detail["deals"][0]["amount"], 8800.0)
        self.assertEqual(detail["deals"][0]["stage"], "lead")
        self.assertEqual(len(detail["follow_ups"]), 2)
        self.assertEqual(
            {f["content"] for f in detail["follow_ups"]},
            {"首次上门量尺", "微信聊了一次"},
        )

    # ---------- 删（级联） ----------
    def test_delete_customer_cascades_deal_and_follow_up(self):
        c = self.create_customer(name="张伟")
        deal_id = insert_deal(c["id"])
        fu_id = insert_follow_up(c["id"], content="带看现场", deal_id=deal_id)

        resp = self.client.delete(f"/api/crm/customers/{c['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)

        self.assertEqual(self.client.get(f"/api/crm/customers/{c['id']}").status_code, 404)
        self.assertEqual(self.client.get("/api/crm/customers").json()["total"], 0)
        with db_conn() as conn:
            self.assertIsNone(
                conn.execute("SELECT 1 FROM deals WHERE id = ?", (deal_id,)).fetchone(),
                "客户的 deals 必须被级联删除",
            )
            self.assertIsNone(
                conn.execute("SELECT 1 FROM follow_ups WHERE id = ?", (fu_id,)).fetchone(),
                "客户的 follow_ups 必须被级联删除",
            )

    def test_update_null_name_rejected(self):
        """name 是 NOT NULL：显式 null 应 400，不能变成 500。"""
        c = self.create_customer(name="张伟")
        resp = self.client.put(f"/api/crm/customers/{c['id']}", json={"name": None})
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(
            self.client.get(f"/api/crm/customers/{c['id']}").json()["name"], "张伟"
        )

    # ---------- 404 / 422 ----------
    def test_missing_customer_returns_404(self):
        self.assertEqual(self.client.get("/api/crm/customers/9999").status_code, 404)
        self.assertEqual(
            self.client.put("/api/crm/customers/9999", json={"name": "x"}).status_code, 404
        )
        self.assertEqual(self.client.delete("/api/crm/customers/9999").status_code, 404)

    def test_create_requires_non_blank_name(self):
        self.assertEqual(self.client.post("/api/crm/customers", json={}).status_code, 422)
        self.assertEqual(
            self.client.post("/api/crm/customers", json={"name": "   "}).status_code, 422
        )

    def test_requires_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get("/api/crm/customers").status_code, 401)
        self.assertEqual(anon.post("/api/crm/customers", json={"name": "x"}).status_code, 401)
        self.assertEqual(anon.delete("/api/crm/customers/1").status_code, 401)


if __name__ == "__main__":
    unittest.main()
