"""T3b：客户标签（多对多 upsert 复用）+ ?tag= 筛选 + /tags 补全 + 复购口径。"""

from __future__ import annotations

import unittest

from tests._util import ApiTestCase, insert_deal, insert_order, open_client

from app.db import db_conn


class TagsTest(ApiTestCase):
    # ---------- 标签 upsert / 复用 ----------
    def test_tag_upsert_reuses_same_tag_id(self):
        a = self.create_customer(name="客户A", tags=["重点"])
        b = self.create_customer(name="客户B", tags=["重点", "转介绍"])

        self.assertEqual(sorted(a["tags"]), ["重点"])
        self.assertEqual(sorted(b["tags"]), sorted(["重点", "转介绍"]))

        # GET /tags 供前端 chips / 自动补全：DISTINCT 去重、按名称排序
        resp = self.client.get("/api/crm/tags")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(sorted(resp.json()), sorted(["重点", "转介绍"]))

        with db_conn() as conn:
            tag_count = conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"]
            link_count = conn.execute("SELECT COUNT(*) AS n FROM customer_tags").fetchone()["n"]
            rows = conn.execute(
                """
                SELECT ct.customer_id, ct.tag_id FROM customer_tags ct
                JOIN tags t ON t.id = ct.tag_id WHERE t.name = '重点'
                """
            ).fetchall()
        self.assertEqual(tag_count, 2, "同名标签只能有一条 tags 记录")
        self.assertEqual(link_count, 3, "A 1 个 + B 2 个关联")
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["tag_id"] for r in rows}), 1, "A/B 的「重点」必须是同一个 tag_id")

    def test_tag_names_are_trimmed_and_deduped(self):
        c = self.create_customer(name="客户D", tags=[" 重点 ", "重点", "", "   "])
        self.assertEqual(c["tags"], ["重点"])
        with db_conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM customer_tags").fetchone()["n"], 1
            )

    def test_popular_tag_limit_uses_customer_usage_count(self):
        for i in range(3):
            self.create_customer(name=f"热门{i}", tags=["热门"])
        for i in range(2):
            self.create_customer(name=f"次热{i}", tags=["次热"])
        self.create_customer(name="少用", tags=["少用"])

        self.assertEqual(
            self.client.get("/api/crm/tags", params={"limit": 2}).json(),
            ["热门", "次热"],
        )

    def test_customer_without_tags(self):
        c = self.create_customer(name="无标签客户")
        self.assertEqual(c["tags"], [])
        with db_conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"], 0)

    # ---------- ?tag= 筛选 ----------
    def test_filter_customers_by_tag(self):
        self.create_customer(name="客户A", tags=["重点"])
        self.create_customer(name="客户B", tags=["重点", "转介绍"])
        self.create_customer(name="客户C", tags=["微信来的"])

        body = self.client.get("/api/crm/customers", params={"tag": "重点"}).json()
        self.assertEqual(body["total"], 2)
        self.assertEqual({c["name"] for c in body["items"]}, {"客户A", "客户B"})
        self.assertTrue(all("重点" in c["tags"] for c in body["items"]))

        body = self.client.get("/api/crm/customers", params={"tag": "转介绍"}).json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["name"], "客户B")

        body = self.client.get("/api/crm/customers", params={"tag": "不存在的标签"}).json()
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["items"], [])

    def test_tag_filter_combined_with_search(self):
        self.create_customer(name="张伟", location="阳光小区", tags=["重点"])
        self.create_customer(name="张敏", location="翡翠湾", tags=["重点"])
        self.create_customer(name="李娜", location="阳光小区", tags=["重点"])

        body = self.client.get(
            "/api/crm/customers", params={"tag": "重点", "search": "阳光"}
        ).json()
        self.assertEqual(body["total"], 2)
        self.assertEqual({c["name"] for c in body["items"]}, {"张伟", "李娜"})

    def test_tag_filter_paginates(self):
        for i in range(5):
            self.create_customer(name=f"重点客户{i}", tags=["重点"])
        self.create_customer(name="普通客户", tags=["普通"])
        body = self.client.get(
            "/api/crm/customers", params={"tag": "重点", "page": 2, "size": 2}
        ).json()
        self.assertEqual(body["total"], 5)
        self.assertEqual(len(body["items"]), 2)

    # ---------- 改标签：先清后插 ----------
    def test_update_replaces_tag_links(self):
        a = self.create_customer(name="客户A", tags=["重点", "转介绍"])
        b = self.create_customer(name="客户B", tags=["重点"])

        resp = self.client.put(f"/api/crm/customers/{a['id']}", json={"tags": ["VIP"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["tags"], ["VIP"])

        with db_conn() as conn:
            a_tags = [
                r["name"]
                for r in conn.execute(
                    """SELECT t.name FROM customer_tags ct JOIN tags t ON t.id = ct.tag_id
                       WHERE ct.customer_id = ? AND ct.is_delete = 0
                       ORDER BY t.name""",
                    (a["id"],),
                )
            ]
        self.assertEqual(a_tags, ["VIP"], "旧关联必须先清掉")

        # B 的「重点」还在；标签字典本身不删（可能别处还在用）
        self.assertEqual(self.client.get("/api/crm/customers", params={"tag": "重点"}).json()["total"], 1)
        self.assertIn("重点", self.client.get("/api/crm/tags").json())

        # 清空标签
        resp = self.client.put(f"/api/crm/customers/{b['id']}", json={"tags": []})
        self.assertEqual(resp.json()["tags"], [])
        self.assertEqual(self.client.get("/api/crm/customers", params={"tag": "重点"}).json()["total"], 0)

    def test_update_without_tags_keeps_existing_tags(self):
        a = self.create_customer(name="客户A", tags=["重点"])
        resp = self.client.put(f"/api/crm/customers/{a['id']}", json={"phone": "13800000001"})
        self.assertEqual(resp.json()["tags"], ["重点"], "没传 tags 不许清空")

    # ---------- 删客户被禁止 → customer_tags 保留 ----------
    def test_delete_customer_is_forbidden_and_keeps_customer_tags(self):
        a = self.create_customer(name="客户A", tags=["重点"])
        self.create_customer(name="客户B", tags=["重点"])

        resp = self.client.delete(f"/api/crm/customers/{a['id']}")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "customer_delete_forbidden")
        with db_conn() as conn:
            left = conn.execute(
                "SELECT COUNT(*) AS n FROM customer_tags"
                " WHERE customer_id = ? AND is_delete = 0",
                (a["id"],),
            ).fetchone()["n"]
            tombstones = conn.execute(
                "SELECT COUNT(*) AS n FROM customer_tags"
                " WHERE customer_id = ? AND is_delete = 1",
                (a["id"],),
            ).fetchone()["n"]
            tag_rows = conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"]
        self.assertGreater(left, 0, "禁止删客户时客户标签必须保留")
        self.assertEqual(tombstones, 0, "禁止删客户时不能产生删除标记")
        self.assertEqual(tag_rows, 1, "标签字典保持原样")
        self.assertEqual(
            self.client.get("/api/crm/customers", params={"tag": "重点"}).json()["total"], 2
        )

    # ---------- 复购口径：deals_total / total_closed_amount ----------
    def test_detail_reports_deals_total_and_closed_amount(self):
        c = self.create_customer(name="复购客户")
        won_deal = insert_deal(
            c["id"], stage="won", amount=2000.0, closed_at="2026-10-01T10:00:00"
        )
        insert_deal(c["id"], stage="lead", amount=900.0)
        insert_order(c["id"], won_deal["id"])

        detail = self.client.get(f"/api/crm/customers/{c['id']}").json()
        self.assertEqual(detail["deals_total"], 2)
        self.assertEqual(detail["orders_total"], 1)
        self.assertEqual(detail["total_closed_amount"], 2000.0, "只累加 won 的金额")
        self.assertTrue(detail["is_repeat"], "deals_total>=2 = 老客口径")
        # 老客只展示，不自动写 tag
        self.assertEqual(detail["tags"], [])

    def test_single_deal_customer_is_not_repeat(self):
        c = self.create_customer(name="新客")
        insert_deal(c["id"], stage="won", amount=500.0)
        detail = self.client.get(f"/api/crm/customers/{c['id']}").json()
        self.assertEqual(detail["deals_total"], 1)
        self.assertEqual(detail["total_closed_amount"], 500.0)
        self.assertFalse(detail["is_repeat"])

    def test_tags_require_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get("/api/crm/tags").status_code, 401)


if __name__ == "__main__":
    unittest.main()
