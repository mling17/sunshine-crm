"""T4：商机管道 —— deals CRUD + 阶段流转（won 置 closed_at）+ 非法阶段 400。"""

from __future__ import annotations

import unittest
from datetime import datetime

from tests._util import ApiTestCase, open_client

from app.models import STAGE_LABELS, STAGES


class DealsTest(ApiTestCase):
    # ---------- 新建 ----------
    def test_create_defaults_to_lead(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=8800.0)

        self.assertEqual(deal["customer_id"], c["id"])
        self.assertEqual(deal["stage"], "lead")
        self.assertEqual(deal["stage_label"], "线索")
        self.assertIsNone(deal["closed_at"])
        self.assertEqual(deal["amount"], 8800.0)
        self.assertEqual(deal["deposit"], 0.0)
        self.assertEqual(deal["balance"], 0.0)
        self.assertIsNone(deal["product_type"])
        self.assertTrue(deal["created_at"] and deal["updated_at"])

    def test_create_with_all_fields(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(
            c["id"],
            product_type="天幕",
            model="TM-300",
            spec="跨度 4m × 3m",
            amount=12000.0,
            deposit=3000.0,
            balance=9000.0,
            stage="quoted",
        )
        self.assertEqual(deal["product_type"], "天幕")
        self.assertEqual(deal["model"], "TM-300")
        self.assertEqual(deal["spec"], "跨度 4m × 3m")
        self.assertEqual(deal["stage"], "quoted")
        self.assertEqual(deal["stage_label"], "已报价")
        self.assertEqual(deal["deposit"], 3000.0)
        self.assertEqual(deal["balance"], 9000.0)
        self.assertIsNone(deal["closed_at"], "只有 won 才写 closed_at")

    def test_create_for_unknown_customer_404(self):
        resp = self.client.post("/api/crm/deals", json={"customer_id": 9999, "amount": 100.0})
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_amount_must_be_non_negative(self):
        c = self.create_customer(name="张伟")
        resp = self.client.post(
            "/api/crm/deals", json={"customer_id": c["id"], "amount": -1}
        )
        self.assertEqual(resp.status_code, 422, resp.text)
        resp = self.client.post("/api/crm/deals", json={"customer_id": c["id"]})
        self.assertEqual(resp.status_code, 422, "amount 必填")

    # ---------- 阶段流转 ----------
    def test_stage_won_sets_and_clears_closed_at(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])

        won = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "won"})
        self.assertEqual(won.status_code, 200, won.text)
        body = won.json()
        self.assertEqual(body["stage"], "won")
        self.assertEqual(body["stage_label"], "已成交")
        self.assertTrue(body["closed_at"], "进入 won 必须置 closed_at")
        closed_at = body["closed_at"]
        # 必须是本地时间口径（T6 的“本月成交”靠它和 localtime 比较）
        self.assertEqual(closed_at[:10], datetime.now().strftime("%Y-%m-%d"))
        self.assertFalse(closed_at.endswith("Z"), "closed_at 用本地时间，不带 UTC 的 Z")

        # won → won（重复提交）不改 closed_at
        again = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "won"}).json()
        self.assertEqual(again["closed_at"], closed_at)

        # 从 won 移出 → closed_at 清空
        shipped = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"stage": "shipped"}
        ).json()
        self.assertEqual(shipped["stage"], "shipped")
        self.assertIsNone(shipped["closed_at"], "从 won 移出必须清空 closed_at")

        # 再回 won → 重新写时间
        rewon = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "won"}).json()
        self.assertTrue(rewon["closed_at"])

    def test_all_stages_are_accepted(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])
        for stage in STAGES:
            resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": stage})
            self.assertEqual(resp.status_code, 200, f"{stage}: {resp.text}")
            self.assertEqual(resp.json()["stage"], stage)
            self.assertEqual(resp.json()["stage_label"], STAGE_LABELS[stage])

    def test_invalid_stage_returns_400(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])

        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "测量中"})
        self.assertEqual(resp.status_code, 400, resp.text)

        resp = self.client.post(
            "/api/crm/deals", json={"customer_id": c["id"], "amount": 1.0, "stage": "nope"}
        )
        self.assertEqual(resp.status_code, 400, resp.text)

        # 非法值不能把库里的阶段改坏
        detail = self.client.get("/api/crm/deals", params={"customer_id": c["id"]}).json()
        self.assertEqual(detail[0]["stage"], "lead")

    # ---------- 改字段 ----------
    def test_partial_update_keeps_other_fields(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, product_type="天窗")

        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"amount": 2500.0})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["amount"], 2500.0)
        self.assertEqual(body["product_type"], "天窗", "没传的字段不许被清空")
        self.assertEqual(body["stage"], "lead")

        # 文本字段可以显式清空
        cleared = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"product_type": None}
        ).json()
        self.assertIsNone(cleared["product_type"])

        # 金额 / 阶段不允许被 null 掉
        for key in ("amount", "stage"):
            resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={key: None})
            self.assertEqual(resp.status_code, 400, f"{key}=null 应 400：{resp.text}")

    def test_update_unknown_deal_404(self):
        resp = self.client.put("/api/crm/deals/9999", json={"amount": 1.0})
        self.assertEqual(resp.status_code, 404, resp.text)

    # ---------- 列表 / 筛选 ----------
    def test_list_filters_by_customer_and_stage(self):
        a = self.create_customer(name="客户A")
        b = self.create_customer(name="客户B")
        d1 = self.create_deal(a["id"], amount=100.0)
        d2 = self.create_deal(a["id"], amount=200.0)
        d3 = self.create_deal(b["id"], amount=300.0)
        self.client.put(f"/api/crm/deals/{d3['id']}", json={"stage": "won"})

        only_a = self.client.get("/api/crm/deals", params={"customer_id": a["id"]})
        self.assertEqual(only_a.status_code, 200, only_a.text)
        self.assertEqual({d["id"] for d in only_a.json()}, {d1["id"], d2["id"]})

        won = self.client.get("/api/crm/deals", params={"stage": "won"}).json()
        self.assertEqual([d["id"] for d in won], [d3["id"]])

        combined = self.client.get(
            "/api/crm/deals", params={"customer_id": a["id"], "stage": "won"}
        ).json()
        self.assertEqual(combined, [])

        all_deals = self.client.get("/api/crm/deals").json()
        self.assertEqual(len(all_deals), 3)

        bad = self.client.get("/api/crm/deals", params={"stage": "bogus"})
        self.assertEqual(bad.status_code, 400, bad.text)

    # ---------- 删客户 → deal 级联（走 API 全链路） ----------
    def test_delete_customer_cascades_deals_via_api(self):
        c = self.create_customer(name="张伟")
        self.create_deal(c["id"], amount=100.0)
        self.create_deal(c["id"], amount=200.0)

        self.assertEqual(self.client.delete(f"/api/crm/customers/{c['id']}").status_code, 200)
        self.assertEqual(
            self.client.get("/api/crm/deals", params={"customer_id": c["id"]}).json(), []
        )

    def test_requires_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get("/api/crm/deals").status_code, 401)
        self.assertEqual(
            anon.post("/api/crm/deals", json={"customer_id": 1, "amount": 1}).status_code, 401
        )
        self.assertEqual(anon.put("/api/crm/deals/1", json={"stage": "won"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
