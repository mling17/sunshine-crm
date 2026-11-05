"""
测试用例：商机订单相关功能（Planner §5.5, §5.6, §6.2, §6.3, §3.5）。
"""
from __future__ import annotations

import unittest
from datetime import datetime

from tests._util import ApiTestCase, open_client

from app.models import STAGE_LABELS, STAGES


class DealOrdersTest(ApiTestCase):
    # ---------- 新建（增强版）----------
    def test_create_defaults_to_quote(self):
        """新商机默认阶段 = quote 报价"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=8800.0, drive_type="electric")
        
        self.assertEqual(deal["customer_id"], c["id"])
        self.assertEqual(deal["stage"], "quote")
        self.assertEqual(deal["stage_label"], "报价")
        self.assertIsNone(deal["closed_at"])
        self.assertEqual(deal["amount"], 8800.0)
        self.assertEqual(deal["deposit"], 0.0)
        self.assertEqual(deal["balance"], 0.0)
        self.assertIsNone(deal["product_type"])
        self.assertIsNone(deal["model"])
        self.assertIsNone(deal["spec"])
        self.assertEqual(deal["drive_type"], "electric")
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
            drive_type="manual"
        )
        self.assertEqual(deal["product_type"], "天幕")
        self.assertEqual(deal["model"], "TM-300")
        self.assertEqual(deal["spec"], "跨度 4m * 3m")
        self.assertEqual(deal["stage"], "quote")
        self.assertEqual(deal["stage_label"], "报价")
        self.assertEqual(deal["deposit"], 0.0)
        self.assertEqual(deal["balance"], 0.0)
        self.assertIsNone(deal["closed_at"], "只有 won 才写 closed_at")
        self.assertEqual(deal["drive_type"], "manual")

    def test_create_requires_drive_type(self):
        """测试创建商机时 drive_type 是必填项"""
        c = self.create_customer(name="张伟")
        resp = self.client.post("/api/crm/deals", json={
            "customer_id": c["id"], 
            "amount": 100.0,
            "product_type": "天窗"
        })
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("drive_type_required", resp.json()["code"])

    def test_create_invalid_drive_type(self):
        """测试创建商机时 drive_type 非法值"""
        c = self.create_customer(name="张伟")
        resp = self.client.post("/api/crm/deals", json={
            "customer_id": c["id"], 
            "amount": 100.0,
            "drive_type": "invalid",
            "product_type": "天窗"
        })
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("invalid_drive_type", resp.json()["code"])

    def test_create_with_note(self):
        """测试创建商机时携带 note"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=100.0, drive_type="electric", note="测试备注")
        self.assertEqual(deal["note"], "测试备注")

    def test_create_with_product_type_validation(self):
        """测试产品类型校验"""
        c = self.create_customer(name="张伟")
        resp = self.client.post("/api/crm/deals", json={
            "customer_id": c["id"], 
            "amount": 100.0,
            "drive_type": "electric",
            "product_type": "不存在的产品类型"
        })
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("invalid_product_type", resp.json()["code"])

    def test_create_with_model_validation(self):
        """测试型号校验"""
        c = self.create_customer(name="张伟")
        resp = self.client.post("/api/crm/deals", json={
            "customer_id": c["id"], 
            "amount": 100.0,
            "drive_type": "electric",
            "model": "不存在的型号"
        })
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("invalid_model", resp.json()["code"])

    # ---------- GET /deals ----------
    def test_spec_separators_normalize_to_star(self):
        """尺寸支持 x/X/×/*，统一以 * 落库。"""
        c = self.create_customer(name="张伟")
        cases = {
            "1000x2000": "1000*2000",
            "1000X2000": "1000*2000",
            "1000×2000": "1000*2000",
            "1000 * 2000": "1000 * 2000",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                deal = self.create_deal(
                    c["id"], amount=100.0, drive_type="electric", spec=raw
                )
                self.assertEqual(deal["spec"], expected)

        deal = self.create_deal(
            c["id"], amount=100.0, drive_type="electric", spec="1000x2000"
        )
        resp = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"spec": "1200X2400"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["spec"], "1200*2400")

    def test_list_deals_exclude_title(self):
        """测试列表接口不返回 title 字段"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=100.0, drive_type="electric")
        
        resp = self.client.get("/api/crm/deals")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertNotIn("title", data[0])

    def test_list_deals_with_drive_type_labels(self):
        """测试列表接口返回 drive_type_label"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=100.0, drive_type="electric")
        
        resp = self.client.get("/api/crm/deals")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertIn("drive_type_label", data[0])
        self.assertEqual(data[0]["drive_type_label"], "电动")

    def test_list_deals_locked_field(self):
        """测试列表接口返回 locked 字段"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=100.0, drive_type="electric")
        
        # 未生成订单时 locked 应为 False
        resp = self.client.get("/api/crm/deals")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertFalse(data[0]["locked"])
        
        # 生成订单后 locked 应为 True
        self.client.post(f"/api/crm/deals/{deal['id']}/win")
        resp = self.client.get("/api/crm/deals")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]["locked"])
        self.assertEqual(data[0]["stage_label"], "已生成订单")

        detail = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(detail["stage_label"], "已生成订单")

    # ---------- GET /deals/{id} ----------
    def test_get_deal_detail_include_timeline(self):
        """测试详情接口包含 timeline"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=100.0, drive_type="electric")
        
        resp = self.client.get(f"/api/crm/deals/{deal['id']}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("timeline", data)
        self.assertIsInstance(data["timeline"], list)
        self.assertIn("order", data)
        self.assertIn("locked", data)
        # 不应该包含 title 字段
        self.assertNotIn("title", data)

    # ---------- 商机修改（锁定矩阵）----------
    def test_update_deal_locked_fields_fails(self):
        """测试商机归档后所有修改失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, drive_type="electric")
        self.client.post(f"/api/crm/deals/{deal['id']}/win")
        
        # 修改金额应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"amount": 2000.0})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

        # 修改 spec 应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"spec": "新规格"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

        # 修改 model 应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"model": "新型号"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

        # 修改 drive_type 应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"drive_type": "manual"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

        # 修改 product_type 应该失败
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"product_type": "新产品"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

        # 生成订单后备注也属于存档内容
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"note": "归档后补备注"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_locked")

    def test_update_deal_unlocked_fields_allowed(self):
        """测试未锁定时修改非关键字段允许"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, drive_type="electric")
        
        # 修改 note 应该成功
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"note": "新的备注"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["note"], "新的备注")

        # 推进阶段应该成功
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stage"], "confirm")

    def test_update_deal_note_records_old_and_new_value(self):
        """备注是可编辑业务字段，必须写清原值与新值。"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(
            c["id"],
            amount=1000.0,
            drive_type="electric",
            note="旧备注",
        )

        resp = self.client.put(
            f"/api/crm/deals/{deal['id']}",
            json={"note": "客户要求周五安装"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        data = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        change = next(item for item in data["timeline"] if item["type"] == "change")
        self.assertEqual(
            change["content"],
            "备注由「旧备注」改为「客户要求周五安装」",
        )
        self.assertEqual(change["detail"]["note"]["from"], "旧备注")
        self.assertEqual(change["detail"]["note"]["to"], "客户要求周五安装")

    def test_update_deal_field_change_timeline(self):
        """测试字段变更记录到 timeline"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, drive_type="electric", spec="1000x2000")
        
        # 修改规格
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"spec": "1200x2400"})
        self.assertEqual(resp.status_code, 200)
        
        # 检查 timeline
        resp = self.client.get(f"/api/crm/deals/{deal['id']}")
        data = resp.json()
        changes = [t for t in data["timeline"] if t["type"] == "change"]
        self.assertEqual(len(changes), 1, "只应有一条编辑履历")
        self.assertEqual(changes[0]["content"], "尺寸由「1000*2000」改为「1200*2400」")
        self.assertIn("create", [t["type"] for t in data["timeline"]], "创建履历必须存在")

    def test_update_deal_stage_change_timeline(self):
        """测试阶段变更记录到 timeline"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, drive_type="electric")
        
        # 推进阶段
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        self.assertEqual(resp.status_code, 200)
        
        # 检查 timeline
        resp = self.client.get(f"/api/crm/deals/{deal['id']}")
        data = resp.json()
        stages = [t for t in data["timeline"] if t["type"] == "stage"]
        self.assertEqual(len(stages), 1, "只应有一条阶段履历")
        self.assertEqual(stages[0]["content"], "阶段推进：报价 → 待客户确认")

    def test_update_deal_no_change_no_timeline(self):
        """测试字段无变更时不记录 timeline"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=1000.0, drive_type="electric", spec="1000x2000")
        
        # 修改为相同的值
        resp = self.client.put(f"/api/crm/deals/{deal['id']}", json={"spec": "1000X2000"})
        self.assertEqual(resp.status_code, 200)
        
        # 检查 timeline
        resp = self.client.get(f"/api/crm/deals/{deal['id']}")
        data = resp.json()
        self.assertEqual([t for t in data["timeline"] if t["type"] == "change"], [],
                         "同值保存不应产生编辑履历")

    # ---------- 生成订单 POST /deals/{id}/orders ----------
    def test_create_order_default_stage_quote_fails(self):
        """测试报价阶段生成订单失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 3600,
            "logistics_mode": "self"
        })
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "deal_not_ready")

    def test_create_order_success(self):
        """测试生成订单成功"""
        carrier = self.create_carrier()
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        
        # 先推进阶段
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 3600,
            "logistics_mode": "agent",
            "carrier_id": carrier["id"],
            "carrier_contact_id": carrier["contacts"][0]["id"],
            "logistics_fee": 800,
            "receiver_name": "张三",
            "receiver_phone": "13800000000",
            "receiver_address": "济南"
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        
        # 检查订单信息
        self.assertIn("order", data)
        order = data["order"]
        self.assertIsNotNone(order["order_no"])
        self.assertRegex(order["order_no"], r"^SO-\d{8}-\d{3}$")
        self.assertEqual(order["product_total"], 12000.0)
        self.assertEqual(order["product_payable"], 12000.0)
        self.assertEqual(order["amount"], 12800.0)
        self.assertEqual(order["deposit_amount"], 3600.0)
        self.assertEqual(order["balance_amount"], 9200.0)
        self.assertEqual(order["status"], "pending_confirmation")
        self.assertEqual(order["receiver_name"], "张三")
        self.assertEqual(order["receiver_phone"], "13800000000")
        self.assertEqual(order["receiver_address"], "济南")
        self.assertEqual(order["carrier_id"], carrier["id"])
        self.assertEqual(order["logistics_fee"], 800.0)
        
        # 检查商机信息
        self.assertIn("deal", data)
        deal_data = data["deal"]
        self.assertEqual(deal_data["stage"], "confirm")
        self.assertIsNone(deal_data["closed_at"])
        self.assertIsNotNone(deal_data["order_id"])
        self.assertIsNotNone(deal_data["locked_at"])

    def test_order_total_always_uses_deal_quote(self):
        """生成订单时的总额固定取商机报价，不能被请求中的 amount 改写。"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})

        resp = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={
                "amount": 1.0,
                "deposit": 3600,
                "logistics_mode": "self",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        order = resp.json()["order"]
        self.assertEqual(order["amount"], 12000.0)
        self.assertEqual(order["deposit_amount"], 3600.0)
        self.assertEqual(order["balance_amount"], 8400.0)

    def test_deposit_and_balance_cannot_be_edited_on_deal(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        for field in ("deposit", "balance"):
            with self.subTest(field=field):
                resp = self.client.put(
                    f"/api/crm/deals/{deal['id']}",
                    json={field: 3000},
                )
                self.assertEqual(resp.status_code, 400, resp.text)

    def test_create_order_balance_calculation(self):
        """测试订单余额计算正确"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        
        # 先推进阶段
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        
        # 测试 deposit=0 情况（全款尾款）
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 0,
            "logistics_mode": "self"
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["order"]["balance_amount"], 12000.0)
        self.assertEqual(data["order"]["deposit_amount"] + data["order"]["balance_amount"], 12000.0)

        # 测试 deposit=amount 情况（一次付清）→ 必须另开一单商机，订单与商机 1:1
        deal2 = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal2['id']}", json={"stage": "confirm"})
        resp = self.client.post(f"/api/crm/deals/{deal2['id']}/orders", json={
            "deposit": 12000.0,
            "logistics_mode": "self"
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["order"]["balance_amount"], 0.0)
        self.assertEqual(data["order"]["deposit_amount"], 12000.0)

    def test_create_order_invalid_deposit_fails(self):
        """测试订单押金超出范围失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        
        # 测试 deposit > amount
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 15000,
            "logistics_mode": "self"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_deposit")

    def test_create_order_missing_carrier_id_fails(self):
        """测试缺少物流公司ID失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        
        # 测试 logistics_mode=agent 但没有 carrier_id
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 3600,
            "logistics_mode": "agent",
            "logistics_fee": 800,
            "receiver_name": "张三",
            "receiver_phone": "13800000000",
            "receiver_address": "济南"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "carrier_required")

    def test_create_order_timeline_contains_all_types(self):
        """测试订单生成后 timeline 包含所有类型"""
        carrier = self.create_carrier()
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 3600,
            "logistics_mode": "agent",
            "carrier_id": carrier["id"],
            "carrier_contact_id": carrier["contacts"][0]["id"],
            "logistics_fee": 800,
            "receiver_name": "张三",
            "receiver_phone": "13800000000",
            "receiver_address": "济南"
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        
        # 检查 timeline
        resp = self.client.get(f"/api/crm/deals/{deal['id']}")
        data = resp.json()
        timeline_types = [item["type"] for item in data["timeline"]]
        # 应该包含 create, stage, order 类型
        self.assertIn("create", timeline_types)
        self.assertIn("stage", timeline_types)
        self.assertIn("order", timeline_types)

    def test_create_order_with_existing_order_fails(self):
        """测试已有订单的商机生成订单失败"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        
        # 第一次生成订单
        self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 3600,
            "logistics_mode": "self"
        })
        
        # 再次生成订单应该失败
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/orders", json={
            "deposit": 3600,
            "logistics_mode": "self"
        })
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "order_exists")

    # ---------- 旧端点兼容 POST /deals/{id}/win ----------
    def test_win_endpoint_compat(self):
        """测试旧的 win 端点兼容性"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0, drive_type="electric")
        
        resp = self.client.post(f"/api/crm/deals/{deal['id']}/win")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查返回格式
        self.assertIn("deal", data)
        self.assertIn("order", data)
        self.assertEqual(data["deal"]["stage"], "confirm")
        self.assertEqual(data["deal"]["stage_label"], "已生成订单")
        self.assertIsNotNone(data["deal"]["order_id"])
        self.assertIsNotNone(data["order"]["order_no"])
        self.assertEqual(data["order"]["amount"], 12000.0)
        self.assertEqual(data["order"]["deposit_amount"], 12000.0)
        self.assertEqual(data["order"]["status"], "pending_confirmation")
        self.assertEqual(data["order"]["logistics_mode"], "self")


if __name__ == "__main__":
    unittest.main()
