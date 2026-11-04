"""
测试用例：商机相关功能（Planner §5.2）。
"""
from __future__ import annotations

import unittest
from datetime import datetime

from tests._util import ApiTestCase, open_client

from app.models import STAGE_LABELS, STAGES


class DealsTest(ApiTestCase):
    # ---------- 新建 ----------
    def test_create_defaults_to_quote(self):
        """新商机默认阶段 = quote 报价（PLANNER-V3 §1.1 定稿：报价→待客户确认→成交/流失）。"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=8800.0)

        self.assertEqual(deal["customer_id"], c["id"])
        self.assertEqual(deal["stage"], "quote")
        self.assertEqual(deal["stage_label"], "报价")
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
            stage="quote",
        )
        self.assertEqual(deal["product_type"], "天幕")
        self.assertEqual(deal["model"], "TM-300")
        self.assertEqual(deal["spec"], "跨度 4m * 3m")
        self.assertEqual(deal["stage"], "quote")
        self.assertEqual(deal["stage_label"], "报价")
        self.assertEqual(deal["deposit"], 0.0)
        self.assertEqual(deal["balance"], 0.0)
        self.assertIsNone(deal["closed_at"], "只有 won 才写 closed_at")

    def test_create_deal_upgrades_intent_to_medium_without_downgrading_high(self):
        low = self.create_customer(name="低意向客户", intent_level="low")
        self.create_deal(low["id"])
        low_detail = self.client.get(f"/api/crm/customers/{low['id']}").json()
        self.assertEqual(low_detail["intent_level"], "medium")

        high = self.create_customer(
            name="高意向客户", phone="13900000001", intent_level="high"
        )
        self.create_deal(high["id"])
        high_detail = self.client.get(f"/api/crm/customers/{high['id']}").json()
        self.assertEqual(high_detail["intent_level"], "high")

    def test_deposit_and_balance_cannot_be_set_on_deal(self):
        c = self.create_customer(name="张伟")
        resp = self.client.post(
            "/api/crm/deals",
            json={
                "customer_id": c["id"],
                "amount": 12000.0,
                "deposit": 3000.0,
                "balance": 9000.0,
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("deposit", resp.text)

    def test_create_for_unknown_customer_404(self):
        resp = self.client.post("/api/crm/deals", json={"customer_id": 9999, "amount": 100.0})
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_amount_must_be_non_negative(self):
        c = self.create_customer(name="张伟")
        resp = self.client.post(
            "/api/crm/deals", json={"customer_id": c["id"], "amount": -1}
        )
        self.assertEqual(resp.status_code, 400, resp.text)  # 计划 §2.6：校验失败 400
        resp = self.client.post("/api/crm/deals", json={"customer_id": c["id"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["amount"], 0.0, "新商机只需备注，报价由报价单产生")

    # ---------- 阶段流转 ----------
    def test_manual_stage_won_requires_customer_confirmation(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)

        # 新口径：生成订单不等于成交，必须客户确认后才能进入成交。
        bad = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "won"})
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "stage_via_customer_confirmation")

        won = self.client.post(f"/api/crm/deals/{deal['id']}/win")
        self.assertEqual(won.status_code, 200, won.text)
        body = won.json()["deal"]
        self.assertEqual(body["stage"], "confirm")
        self.assertIsNone(body["closed_at"], "客户确认前不能计为成交")

        # 生成订单后冻结：PUT 改阶段 → 409
        frozen = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "quote"})
        self.assertEqual(frozen.status_code, 409, frozen.text)

    def test_all_stages_are_accepted(self):
        c = self.create_customer(name="张伟")
        # 创建一个初始商机
        deal = self.create_deal(c["id"], amount=10000.0)
        
        # 测试所有有效的阶段（排除won和lost，因为它们是冻结状态）
        for stage in STAGES:
            if stage in ("won", "lost"):
                # won/lost 是冻结状态，不应该被修改
                continue
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
        self.assertEqual(detail[0]["stage"], "quote")

    # ---------- 改字段 ----------
    def test_partial_update_keeps_other_fields(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, product_type="天窗")

        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"amount": 2500.0})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["amount"], 2500.0)
        self.assertEqual(body["product_type"], "天窗", "没传的字段不许被清空")
        self.assertEqual(body["stage"], "quote")

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
        self.client.post(f"/api/crm/deals/{d3['id']}/win")

        only_a = self.client.get("/api/crm/deals", params={"customer_id": a["id"]})
        self.assertEqual(only_a.status_code, 200, only_a.text)
        self.assertEqual({d["id"] for d in only_a.json()}, {d1["id"], d2["id"]})

        confirm = self.client.get("/api/crm/deals", params={"stage": "confirm"}).json()
        self.assertEqual([d["id"] for d in confirm], [d3["id"]])

        combined = self.client.get(
            "/api/crm/deals", params={"customer_id": a["id"], "stage": "won"}
        ).json()
        self.assertEqual(combined, [])

        all_deals = self.client.get("/api/crm/deals").json()
        self.assertEqual(len(all_deals), 3)

        bad = self.client.get("/api/crm/deals", params={"stage": "bogus"})
        self.assertEqual(bad.status_code, 400, bad.text)

    # ---------- 删客户被禁止 → deals 保留 ----------
    def test_delete_customer_is_forbidden_and_keeps_deals(self):
        c = self.create_customer(name="张伟")
        first = self.create_deal(c["id"], amount=100.0)
        second = self.create_deal(c["id"], amount=200.0)

        resp = self.client.delete(f"/api/crm/customers/{c['id']}")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "customer_delete_forbidden")
        self.assertEqual(
            {
                d["id"]
                for d in self.client.get(
                    "/api/crm/deals", params={"customer_id": c["id"]}
                ).json()
            },
            {first["id"], second["id"]},
        )

    def test_requires_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get("/api/crm/deals").status_code, 401)
        self.assertEqual(
            anon.post("/api/crm/deals", json={"customer_id": 1, "amount": 1}).status_code, 401
        )
        self.assertEqual(anon.put("/api/crm/deals/1", json={"stage": "won"}).status_code, 401)

    # ---------- 商机冻结测试 ----------
    def test_get_deal_detail(self):
        """测试获取商机详情"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        resp = self.client.get(f"/api/crm/deals/{deal['id']}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], deal["id"])
        self.assertEqual(data["amount"], 1000.0)

    def test_win_deal_success(self):
        """测试商机赢单成功"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/win")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查返回结果
        self.assertIn("deal", data)
        self.assertIn("order", data)
        self.assertEqual(data["deal"]["stage"], "confirm")
        self.assertIsNotNone(data["deal"]["order_id"])
        self.assertIsNotNone(data["order"]["order_no"])
        self.assertEqual(data["order"]["amount"], 1000.0)
        self.assertEqual(data["order"]["status"], "pending_confirmation")
        
        # 检查订单状态日志
        order_id = data["deal"]["order_id"]
        order_resp = self.client.get(f"/api/crm/orders/{order_id}")
        self.assertEqual(order_resp.status_code, 200)
        order_data = order_resp.json()
        self.assertEqual(len(order_data["status_log"]), 1)
        self.assertEqual(order_data["status_log"][0]["to_status"], "pending_confirmation")

    def test_win_deal_already_won_creates_order(self):
        """已成交但没有订单（异常态）→ /win 补生成订单（不再报错）"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        # 直接落库置 won（模拟历史异常态：赢了但没有订单）
        with self.db_conn() as conn:
            conn.execute("UPDATE deals SET stage='won' WHERE id=?", (deal["id"],))
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/win")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIsNotNone(resp.json()["deal"]["order_id"])

    def test_win_deal_already_has_order_fails(self):
        """测试已有订单的商机赢单失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        # 先赢单生成订单
        self.client.post(f"/api/crm/deals/{deal['id']}/win")
        
        # 再次赢单应该失败
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/win")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "order_exists")

    def test_win_deal_zero_amount_fails(self):
        """测试金额为0的商机赢单失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=0.0)
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/win")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_amount")

    def test_lose_deal_success(self):
        """测试商机流失成功"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/lose", json={
            "lost_reason": "price"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        self.assertEqual(data["stage"], "lost")
        self.assertEqual(data["lost_reason"], "price")
        self.assertIsNone(data["closed_at"])

    def test_lose_deal_invalid_reason_fails(self):
        """测试无效流失原因失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/lose", json={
            "lost_reason": "invalid_reason"
        })
        self.assertEqual(resp.status_code, 400)

    def test_lose_deal_other_reason_requires_description(self):
        """测试流失原因other需要描述"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/lose", json={
            "lost_reason": "other"
        })
        self.assertEqual(resp.status_code, 400)

    def test_update_deal_after_win_fails(self):
        """测试赢单后更新商机失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        # 先赢单
        self.client.post(f"/api/crm/deals/{deal['id']}/win")
        
        # 更新商机应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"amount": 2000.0})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

    def test_update_deal_after_lose_fails(self):
        """测试流失后更新商机失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)
        
        # 先流失
        self.client.post(f"/api/crm/deals/{deal['id']}/lose", json={
            "lost_reason": "price"
        })
        
        # 更新商机应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"amount": 2000.0})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_frozen")

    def test_freeze_matrix_assertions(self):
        """冻结矩阵：① 出单后锁定 ② 锁定后仍可改备注 ③ 流失后冻结 ④ 流失后仍可改备注"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0)

        # ① 生成订单后 → 金额不可改
        self.client.post(f"/api/crm/deals/{deal['id']}/win")
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"amount": 2000.0})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

        # ② 锁定只挡基本信息，备注照常能改
        note = self.client.put(f"/api/crm/deals/{deal['id']}", json={"note": "锁定后补备注"})
        self.assertEqual(note.status_code, 200, note.text)
        self.assertEqual(note.json()["note"], "锁定后补备注")

        # ③ 另一单走流失 → 冻结
        d2 = self.create_deal(c["id"], amount=500.0)
        self.client.post(f"/api/crm/deals/{d2['id']}/lose", json={"lost_reason": "price"})
        resp = self.client.put(f"/api/crm/deals/{d2['id']}", json={"amount": 2000.0})
        self.assertEqual(resp.status_code, 409)

        # ④ 流失后备注仍可改
        note2 = self.client.put(f"/api/crm/deals/{d2['id']}", json={"note": "流失原因跟进"})
        self.assertEqual(note2.status_code, 200, note2.text)


if __name__ == "__main__":
    unittest.main()
