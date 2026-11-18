"""T3：客户档案新建/查询/修改 + 搜索 + 分页 + 详情 + 删除保护。"""

from __future__ import annotations

import unittest

from tests._util import (
    ApiTestCase,
    insert_customer,
    insert_deal,
    insert_follow_up,
    open_client,
)

from app.db import db_conn


class CustomersTest(ApiTestCase):
    def test_direct_customer_creation_is_forbidden_and_writes_nothing(self):
        resp = self.client.post(
            "/api/crm/customers",
            json={"name": "绕过线索的客户", "phone": "13800000009"},
        )

        self.assertEqual(resp.status_code, 405, resp.text)
        self.assertEqual(resp.json()["code"], "customer_create_forbidden")
        self.assertEqual(self.client.get("/api/crm/customers").json()["total"], 0)
        with db_conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 0)

    # ---------- 建 + 列表 ----------
    def test_create_and_list(self):
        a = self.create_customer(
            name="张伟",
            phone="13800000001",
            wechat="zw001",
            location="阳光小区",
            note="三居，主卧朝南",
        )
        self.create_customer(name="李娜", phone="13900000002", location="翡翠湾")

        self.assertIsInstance(a["id"], int)
        self.assertEqual(a["name"], "张伟")
        self.assertEqual(a["phone"], "13800000001")
        self.assertEqual(a["wechat"], "zw001")
        self.assertEqual(a["location"], "阳光小区")
        self.assertEqual(a["note"], "三居，主卧朝南")
        self.assertTrue(a["created_at"])
        self.assertTrue(a["updated_at"])
        # 新客户默认无商机（标签口径在 T3b 的 tests/test_tags.py 覆盖）
        self.assertEqual(a["deals_total"], 0)
        self.assertEqual(a["orders_total"], 0)
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
        # Ticket #10：size 走白名单 [10,20,50,100,500]，最小档 10
        for i in range(25):
            self.create_customer(name=f"客户{i}")

        page1 = self.client.get("/api/crm/customers", params={"page": 1, "size": 10}).json()
        page2 = self.client.get("/api/crm/customers", params={"page": 2, "size": 10}).json()
        page3 = self.client.get("/api/crm/customers", params={"page": 3, "size": 10}).json()
        over = self.client.get("/api/crm/customers", params={"page": 9, "size": 10}).json()

        self.assertEqual((page1["total"], page2["total"], page3["total"]), (25, 25, 25))
        self.assertEqual((len(page1["items"]), len(page2["items"]), len(page3["items"])), (10, 10, 5))
        self.assertEqual(over["items"], [], "页码越界返回空 items，不报错")
        ids = [c["id"] for c in page1["items"] + page2["items"] + page3["items"]]
        self.assertEqual(len(set(ids)), 25, "分页不重不漏")

    # ---------- 改 ----------
    def test_update_rejects_phone_and_preserves_record(self):
        customer_id = insert_customer(
            name="李娜",
            phone="13800000001",
        )
        before = self.client.get(f"/api/crm/customers/{customer_id}").json()

        resp = self.client.put(
            f"/api/crm/customers/{customer_id}",
            json={"phone": "13800000001", "location": "不应写入的新地址"},
        )

        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "customer_phone_immutable")
        after = self.client.get(f"/api/crm/customers/{customer_id}").json()
        self.assertEqual(after["phone"], "13800000001")
        self.assertEqual(after["location"], before["location"])
        self.assertEqual(after["updated_at"], before["updated_at"])

    def test_update_fields(self):
        c = self.create_customer(name="张伟", location="旧地址")

        resp = self.client.put(
            f"/api/crm/customers/{c['id']}",
            json={"location": "新地址", "wechat": "new-wechat"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        updated = resp.json()
        self.assertEqual(updated["location"], "新地址")
        self.assertEqual(updated["wechat"], "new-wechat")
        self.assertEqual(updated["phone"], c["phone"])
        # 没传的字段不许被清空
        self.assertEqual(updated["name"], "张伟")
        self.assertEqual(updated["id"], c["id"])

        detail = self.client.get(f"/api/crm/customers/{c['id']}").json()
        self.assertEqual(detail["location"], "新地址")

    def test_update_writes_field_level_history(self):
        c = self.create_customer(
            name="张伟",
            location="旧地址",
            tags=["重点"],
        )
        resp = self.client.put(
            f"/api/crm/customers/{c['id']}",
            json={
                "location": "新地址",
                "tags": ["门店", "待量尺"],
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        history = self.client.get(
            "/api/crm/follow-ups",
            params={
                "object_type": "customer",
                "object_id": c["id"],
                "include_system": "true",
            },
        ).json()["items"]
        change = next(item for item in history if item["kind"] == "change")
        self.assertEqual(
            change["content"],
            "地区由「旧地址」改为「新地址」；"
            "标签由「重点」改为「门店、待量尺」",
        )

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
        self.assertEqual(detail["deals"][0]["stage"], "confirm")
        self.assertEqual(len(detail["follow_ups"]), 2)
        self.assertEqual(
            {f["content"] for f in detail["follow_ups"]},
            {"首次上门量尺", "微信聊了一次"},
        )

    # ---------- 删（禁止） ----------
    def test_delete_customer_is_forbidden_and_keeps_related_data(self):
        c = self.create_customer(name="张伟")
        deal_id = insert_deal(c["id"])
        fu_id = insert_follow_up(c["id"], content="带看现场", deal_id=deal_id)

        resp = self.client.delete(f"/api/crm/customers/{c['id']}")
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(resp.json()["code"], "customer_delete_forbidden")

        self.assertEqual(self.client.get(f"/api/crm/customers/{c['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/crm/customers").json()["total"], 1)
        with db_conn() as conn:
            self.assertEqual(
                conn.execute("SELECT is_delete FROM deals WHERE id = ?", (deal_id,)).fetchone()[0],
                0,
                "禁止删客户时商机不能受影响",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT is_delete FROM follow_ups WHERE id = ?", (fu_id,)
                ).fetchone()[0],
                0,
                "禁止删客户时跟进记录不能受影响",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT is_delete FROM customers WHERE id = ?", (c["id"],)
                ).fetchone()[0],
                0,
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
        self.assertEqual(self.client.delete("/api/crm/customers/9999").status_code, 403)

    def test_direct_customer_creation_is_forbidden_for_any_payload(self):
        for payload in ({}, {"name": "   "}):
            with self.subTest(payload=payload):
                resp = self.client.post("/api/crm/customers", json=payload)
                self.assertEqual(resp.status_code, 405, resp.text)
                self.assertEqual(resp.json()["code"], "customer_create_forbidden")

    def test_requires_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get("/api/crm/customers").status_code, 401)
        self.assertEqual(anon.post("/api/crm/customers", json={"name": "x"}).status_code, 401)
        self.assertEqual(anon.delete("/api/crm/customers/1").status_code, 401)


class CustomersListPaginationSortTest(ApiTestCase):
    """Ticket #10：客户列表分页/排序白名单 + last_follow 派生（与线索页 Ticket #9 同口径）。"""

    def post_follow_up(self, customer_id: int, *, content: str = "电话沟通") -> int:
        resp = self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "customer",
                "object_id": str(customer_id),
                "content": content,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return int(resp.json()["id"])

    def set_follow_created_at(self, follow_up_id: int, created_at: str) -> None:
        with db_conn() as conn:
            conn.execute(
                "UPDATE follow_ups SET created_at = ? WHERE id = ?",
                (created_at, follow_up_id),
            )

    # ---------- page / size 白名单 ----------
    def test_size_whitelist(self):
        for i in range(15):
            self.create_customer(name=f"白名单客户{i}")
        for size in (10, 20, 50, 100, 500):
            resp = self.client.get("/api/crm/customers", params={"size": size})
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["size"], size)
        for bad in (0, 1, 15, 200, 501, -10):
            resp = self.client.get("/api/crm/customers", params={"size": bad})
            self.assertEqual(resp.status_code, 400, f"size={bad}")
            self.assertEqual(resp.json()["code"], "invalid_page_size")

    def test_page_must_be_positive(self):
        self.create_customer(name="分页客户")
        for bad in (0, -1):
            resp = self.client.get("/api/crm/customers", params={"page": bad})
            self.assertEqual(resp.status_code, 400, f"page={bad}")
            self.assertEqual(resp.json()["code"], "invalid_page")
        resp = self.client.get("/api/crm/customers")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["size"], 20)  # 默认 20

    # ---------- sort / order 白名单 ----------
    def test_invalid_sort_or_order_400(self):
        self.create_customer(name="排序客户")
        for url in (
            "/api/crm/customers?sort=phone",
            "/api/crm/customers?sort=name;DROP TABLE customers",
            "/api/crm/customers?sort=created_at&order=up",
            "/api/crm/customers?sort=location&order=1 desc",
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400, resp.text)

    def test_default_order_is_id_desc(self):
        ids = []
        for i in range(3):
            ids.append(self.create_customer(name=f"默认{i}")["id"])
        body = self.client.get("/api/crm/customers?size=500").json()
        self.assertEqual([c["id"] for c in body["items"]], list(reversed(ids)))

    def test_explicit_sort_uses_id_desc_tiebreak(self):
        ids = []
        for i in range(3):
            ids.append(self.create_customer(name=f"稳定{i}")["id"])
        # 三条 created_at 压成同一秒：显式排序必须有稳定次键 id DESC（最新建的在前）
        with db_conn() as conn:
            conn.execute(
                "UPDATE customers SET created_at = '2026-11-18T00:00:00Z'"
                " WHERE id IN (?, ?, ?)",
                tuple(ids),
            )
        body = self.client.get(
            "/api/crm/customers?sort=created_at&order=asc&size=500"
        ).json()
        self.assertEqual([c["id"] for c in body["items"]], list(reversed(ids)))

    def test_sort_by_name(self):
        self.create_customer(name="张伟")
        self.create_customer(name="李娜")
        # SQLite 默认 BINARY 排序按 UTF-8 字节序：张(0x5F20) < 李(0x674E)
        body = self.client.get(
            "/api/crm/customers?sort=name&order=asc&size=500"
        ).json()
        self.assertEqual([c["name"] for c in body["items"]], ["张伟", "李娜"])
        body = self.client.get(
            "/api/crm/customers?sort=name&order=desc&size=500"
        ).json()
        self.assertEqual([c["name"] for c in body["items"]], ["李娜", "张伟"])

    def test_sort_by_nullable_location_nulls_last(self):
        self.create_customer(name="杭州客户", location="杭州")
        self.create_customer(name="北京客户", location="北京")
        self.create_customer(name="无地区客户")

        body = self.client.get(
            "/api/crm/customers?sort=location&order=asc&size=500"
        ).json()
        names = [c["name"] for c in body["items"]]
        self.assertEqual(names[:2], ["北京客户", "杭州客户"])
        self.assertEqual(names[-1], "无地区客户")

        body = self.client.get(
            "/api/crm/customers?sort=location&order=desc&size=500"
        ).json()
        names = [c["name"] for c in body["items"]]
        self.assertEqual(names[:2], ["杭州客户", "北京客户"])
        self.assertEqual(names[-1], "无地区客户")

    # ---------- last_follow 派生 ----------
    def test_last_follow_field_derivation(self):
        early = self.create_customer(name="早跟进客户")
        late = self.create_customer(name="晚跟进客户")
        none = self.create_customer(name="无跟进客户")

        early_fu = self.post_follow_up(early["id"], content="第一次")
        self.set_follow_created_at(early_fu, "2026-11-01T09:00:00Z")
        self.post_follow_up(early["id"], content="第二次")
        self.post_follow_up(late["id"], content="仅一次")

        body = self.client.get("/api/crm/customers?size=500").json()
        by_name = {c["name"]: c for c in body["items"]}

        self.assertIsNone(by_name["无跟进客户"]["last_follow"])
        # 取最新一条人工跟进，不是第一条
        self.assertNotEqual(
            by_name["早跟进客户"]["last_follow"], "2026-11-01T09:00:00Z"
        )
        self.assertTrue(by_name["晚跟进客户"]["last_follow"])
        self.assertGreater(
            by_name["晚跟进客户"]["last_follow"],
            "2026-11-01T09:00:00Z",
        )

    def test_last_follow_ignores_non_follow_kind(self):
        c = self.create_customer(name="系统履历客户")
        # 系统履历（kind != 'follow'，如编辑档案产生的 change 记录）不算人工跟进
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO follow_ups
                    (object_type, object_id, customer_id, kind, content, created_at)
                VALUES ('customer', ?, ?, 'change', '修改档案', '2026-11-02T10:00:00Z')
                """,
                (c["id"], c["id"]),
            )
        body = self.client.get("/api/crm/customers?size=500").json()
        item = next(i for i in body["items"] if i["name"] == "系统履历客户")
        self.assertIsNone(item["last_follow"])

    def test_sort_by_last_follow_nulls_last_both_directions(self):
        early = self.create_customer(name="早跟进")
        late = self.create_customer(name="晚跟进")
        self.create_customer(name="无跟进")
        early_fu = self.post_follow_up(early["id"], content="早")
        self.set_follow_created_at(early_fu, "2026-11-01T09:00:00Z")
        late_fu = self.post_follow_up(late["id"], content="晚")
        self.set_follow_created_at(late_fu, "2026-11-10T09:00:00Z")

        body = self.client.get(
            "/api/crm/customers?sort=last_follow&order=asc&size=500"
        ).json()
        self.assertEqual(
            [c["name"] for c in body["items"]], ["早跟进", "晚跟进", "无跟进"]
        )

        body = self.client.get(
            "/api/crm/customers?sort=last_follow&order=desc&size=500"
        ).json()
        self.assertEqual(
            [c["name"] for c in body["items"]], ["晚跟进", "早跟进", "无跟进"]
        )

    def test_sort_by_type_intent_created_at(self):
        self.create_customer(
            name="公司甲", customer_type="company", intent_level="high"
        )
        self.create_customer(
            name="个人乙", customer_type="personal", intent_level="low"
        )
        for sort in ("type", "intent", "created_at"):
            for order in ("asc", "desc"):
                resp = self.client.get(
                    "/api/crm/customers",
                    params={"sort": sort, "order": order, "size": 500},
                )
                self.assertEqual(resp.status_code, 200, f"{sort}/{order}")
                self.assertEqual(len(resp.json()["items"]), 2)


if __name__ == "__main__":
    unittest.main()
