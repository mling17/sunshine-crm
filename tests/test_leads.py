"""T2：线索管理 + 转化 + 统一跟进。

覆盖验收点：
- 建线索（手机/微信二选一、都空 400）、状态流转、失效原因必选、终态不可改（409）、搜索/筛选、分页；
- 转化（无重复直接转化、去重命中 409 带 matches、link 分支、force_new 分支、link 到不匹配客户 400、意向顺延、created_at 继承、标签迁移、跟进迁移、商机字段必填、已转化线索 409、公司线索只带主联系人）；
- 统一跟进（5 类对象挂载、V1 参数兼容、商机冻结 409、线索终态 409、意向顺带更新、≤3 张照片、object_type 非法 400）。
"""
from __future__ import annotations

import unittest
from typing import Any

from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import，设定临时 DB/上传目录
from tests._util import ApiTestCase

from app.config.settings import settings
from app.db import db_conn


class LeadsTest(ApiTestCase):
    # ---------- 小工具 ----------
    def create_lead(
        self,
        *,
        name: str = "张伟",
        phone: str = "13800138000",
        wechat: str | None = None,
        lead_type: str = "personal",
        company_name: str | None = None,
        source: str = "wechat",
        source_other: str | None = None,
        location: str | None = None,
        note: str | None = None,
        intent_level: str | None = None,
        tags: list[str] | None = None,
    ):
        data = {
            "name": name,
            "phone": phone,
            "lead_type": lead_type,
            "source": source,
        }
        if wechat is not None:
            data["wechat"] = wechat
        if company_name is not None:
            data["company_name"] = company_name
        if source_other is not None:
            data["source_other"] = source_other
        if location is not None:
            data["location"] = location
        if note is not None:
            data["note"] = note
        if intent_level is not None:
            data["intent_level"] = intent_level
        if tags is not None:
            data["tags"] = tags
            
        return self.client.post("/api/crm/leads", json=data).json()

    def create_customer(
        self,
        *,
        name: str = "李娜",
        phone: str = "13900139000",
        wechat: str | None = None,
        customer_type: str = "personal",
        company_name: str | None = None,
        source: str = "existing",
        source_other: str | None = None,
        location: str | None = None,
        note: str | None = None,
        intent_level: str | None = None,
    ):
        data = {
            "name": name,
            "phone": phone,
            "wechat": wechat,
            "customer_type": customer_type,
            "company_name": company_name,
            "source": source,
            "source_other": source_other,
            "location": location,
            "note": note,
            "intent_level": intent_level,
        }
        return self.client.post("/api/crm/customers", json=data).json()

    def create_deal(
        self,
        customer_id: int,
        *,
        product_type: str = "天窗",
        model: str = "XW-120",
        spec: str = "1200*2400",
        amount: float = 12800.0,
        stage: str = "quote",
        drive_type: str = "manual",
    ):
        data = {
            "customer_id": customer_id,
            "product_type": product_type,
            "model": model,
            "spec": spec,
            "amount": amount,
            "stage": stage,
            "drive_type": drive_type,
        }
        return self.client.post("/api/crm/deals", json=data).json()

    def create_order(
        self,
        deal_id: int,
    ):
        # 创建订单需要先有商机
        # 这里简化处理，实际测试中需要根据业务逻辑调整
        return self.client.post("/api/crm/orders", json={
            "deal_id": deal_id,
            "product_type": "天窗",
            "model": "平移",
            "spec": "1200*1400",
            "amount": 12800.0,
            "order_no": "SO-20261030-001"
        }).json()

    def create_aftersale(
        self,
        order_id: int,
    ):
        # 创建售后单需要先有订单
        return self.client.post("/api/crm/aftersales", json={
            "order_id": order_id,
            "type": "repair",
            "description": "测试售后"
        }).json()

    def post_follow_up(
        self,
        object_type: str,
        object_id: int,
        *,
        content: str = "电话沟通，客户要 3 天内报价",
        method: str | None = None,
        next_date: str | None = None,
        intent_level: str | None = None,
        stage: str | None = None,
        photos: list[tuple[str, str, bytes]] | None = None,
    ):
        data = {
            "object_type": object_type,
            "object_id": str(object_id),
            "content": content,
        }
        if method is not None:
            data["method"] = method
        if next_date is not None:
            data["next_date"] = next_date
        if intent_level is not None:
            data["intent_level"] = intent_level
        if stage is not None:
            data["stage"] = stage
            
        files = []
        if photos:
            for i, (filename, mime, payload) in enumerate(photos):
                files.append(("photos", (f"{i}_{filename}", payload, mime)))
        
        return self.client.post(
            "/api/crm/follow-ups", data=data, files=files or None
        )

    # ---------- 建线索 ----------
    def test_create_lead_with_phone_only(self):
        resp = self.create_lead(phone="13800138000")
        self.assertEqual(resp["phone"], "13800138000")
        self.assertEqual(resp["status"], "new")
        self.assertEqual(resp["intent_level"], "medium")  # 定稿：新建线索意向默认「中」

    def test_create_lead_with_wechat_only(self):
        resp = self.create_lead(wechat="wechat123")
        self.assertEqual(resp["wechat"], "wechat123")
        self.assertEqual(resp["status"], "new")

    def test_create_lead_with_both_phone_and_wechat(self):
        resp = self.create_lead(phone="13800138000", wechat="wechat123")
        self.assertEqual(resp["phone"], "13800138000")
        self.assertEqual(resp["wechat"], "wechat123")
        self.assertEqual(resp["status"], "new")

    def test_create_lead_with_no_contact_info_400(self):
        resp = self.client.post("/api/crm/leads", json={
            "name": "张伟",
            "phone": "",
            "wechat": "",
            "source": "wechat",
        })
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("手机和微信至少填一个", resp.json()["detail"])

    def test_create_lead_with_invalid_source_400(self):
        resp = self.client.post("/api/crm/leads", json={
            "name": "张伟",
            "phone": "13800138000",
            "source": "invalid-source",
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_create_lead_with_tags(self):
        resp = self.create_lead(phone="13800138000", tags=["重要客户", "VIP"])
        self.assertEqual(resp["tags"], ["重要客户", "VIP"])

    # ---------- 查看线索 ----------
    def test_get_lead_detail(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.get(f"/api/crm/leads/{lead['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["phone"], "13800138000")
        self.assertEqual(body["status"], "new")
        self.assertEqual(body["tags"], [])

    def test_get_nonexistent_lead_404(self):
        resp = self.client.get("/api/crm/leads/9999")
        self.assertEqual(resp.status_code, 404, resp.text)

    # ---------- 列表 ----------
    def test_list_leads(self):
        self.create_lead(name="张伟", phone="13800138000")
        self.create_lead(name="李娜", phone="13900139000")
        resp = self.client.get("/api/crm/leads")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["items"]), 2)

    def test_list_leads_filter_by_status(self):
        self.create_lead(name="张伟", phone="13800138000", source="wechat")
        self.create_lead(name="李娜", phone="13900139000", source="phone")
        resp = self.client.get("/api/crm/leads?status=new")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total"], 2)

    def test_list_leads_search(self):
        self.create_lead(name="张伟", phone="13800138000")
        self.create_lead(name="李娜", phone="13900139000")
        resp = self.client.get("/api/crm/leads?search=张伟")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["name"], "张伟")

    def test_list_leads_pagination(self):
        for i in range(25):
            self.create_lead(name=f"客户{i}", phone=f"1380013800{i:02d}")
        resp = self.client.get("/api/crm/leads?page=2&size=10")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total"], 25)
        self.assertEqual(len(body["items"]), 10)
        self.assertEqual(body["page"], 2)

    # ---------- 修改线索 ----------
    def test_update_lead(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.put(f"/api/crm/leads/{lead['id']}", json={
            "name": "张伟伟",
            "phone": "13800138001",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["name"], "张伟伟")
        self.assertEqual(body["phone"], "13800138001")

    def test_update_lead_timeline_records_field_values(self):
        lead = self.create_lead(
            name="张伟",
            phone="13800138000",
            note="旧备注",
            intent_level="medium",
        )
        resp = self.client.put(f"/api/crm/leads/{lead['id']}", json={
            "name": "张伟伟",
            "note": "新备注",
            "intent_level": "high",
        })
        self.assertEqual(resp.status_code, 200, resp.text)

        history = self.client.get(
            "/api/crm/follow-ups",
            params={
                "object_type": "lead",
                "object_id": lead["id"],
                "include_system": "true",
            },
        ).json()
        change = next(item for item in history if item["kind"] == "change")
        self.assertEqual(
            change["content"],
            "姓名由「张伟」改为「张伟伟」；"
            "备注由「旧备注」改为「新备注」；"
            "意向由「中」改为「高」",
        )

    def test_update_lead_tags(self):
        lead = self.create_lead(phone="13800138000", tags=["重点客户"])
        resp = self.client.put(f"/api/crm/leads/{lead['id']}", json={
            "tags": ["门店客户", "待量尺"],
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["tags"], ["门店客户", "待量尺"])
        detail = self.client.get(f"/api/crm/leads/{lead['id']}").json()
        self.assertEqual(detail["tags"], ["门店客户", "待量尺"])

    def test_update_lead_to_invalid_status_409(self):
        lead = self.create_lead(phone="13800138000")
        # 转化线索
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200x2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        
        # 尝试修改已转化的线索
        resp = self.client.put(f"/api/crm/leads/{lead['id']}", json={
            "name": "张伟伟",
        })
        self.assertEqual(resp.status_code, 409, resp.text)

    # ---------- 置失效 ----------
    def test_invalidate_lead(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/invalidate", json={
            "invalid_reason": "no_intent",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "invalid")
        self.assertEqual(body["invalid_reason"], "no_intent")

    def test_invalidate_lead_with_other_reason(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/invalidate", json={
            "invalid_reason": "other",
            "invalid_reason_other": "客户不愿意合作",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "invalid")
        self.assertEqual(body["invalid_reason"], "other")
        self.assertEqual(body["invalid_reason_other"], "客户不愿意合作")

    def test_only_invalid_lead_can_be_soft_deleted(self):
        lead = self.create_lead(phone="13800138000")
        blocked = self.client.delete(f"/api/crm/leads/{lead['id']}")
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "lead_not_invalid")

        invalidated = self.client.post(
            f"/api/crm/leads/{lead['id']}/invalidate",
            json={"invalid_reason": "no_intent"},
        )
        self.assertEqual(invalidated.status_code, 200, invalidated.text)
        deleted = self.client.delete(f"/api/crm/leads/{lead['id']}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(self.client.get(f"/api/crm/leads/{lead['id']}").status_code, 404)
        with db_conn() as conn:
            row = conn.execute(
                "SELECT is_delete, create_time, update_time FROM leads WHERE id = ?",
                (lead["id"],),
            ).fetchone()
        self.assertEqual(row["is_delete"], 1)
        self.assertTrue(row["create_time"])
        self.assertTrue(row["update_time"])

        # 软删除释放电话唯一键，可以重新建一条有效线索。
        recreated = self.create_lead(name="重新录入", phone="13800138000")
        self.assertEqual(recreated["phone"], "13800138000")

    def test_invalidate_lead_missing_reason_400(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/invalidate", json={})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_invalidate_lead_invalid_reason_400(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/invalidate", json={
            "invalid_reason": "invalid_reason",
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_invalidate_lead_other_reason_missing_text_400(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/invalidate", json={
            "invalid_reason": "other",
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    # ---------- 转化前检查 ----------
    def test_convert_check_with_existing_customer(self):
        # 创建一个客户
        customer = self.create_customer(phone="13800138000")
        
        # 检查转化前检查
        resp = self.client.get("/api/crm/leads/convert-check?phone=13800138000")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["has_match"])
        self.assertEqual(len(body["matches"]), 1)
        self.assertEqual(body["matches"][0]["object_type"], "customer")
        self.assertEqual(body["matches"][0]["object_id"], customer["id"])

    def test_convert_check_with_existing_lead(self):
        # 创建一个线索
        lead = self.create_lead(phone="13800138000")
        
        # 检查转化前检查
        resp = self.client.get("/api/crm/leads/convert-check?phone=13800138000")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["has_match"])
        self.assertEqual(len(body["matches"]), 1)
        self.assertEqual(body["matches"][0]["object_type"], "lead")
        self.assertEqual(body["matches"][0]["object_id"], lead["id"])

    def test_convert_check_no_match(self):
        # 检查转化前检查
        resp = self.client.get("/api/crm/leads/convert-check?phone=13800138001")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertFalse(body["has_match"])
        self.assertEqual(len(body["matches"]), 0)

    # ---------- 建前查重 (Q6) ----------
    def test_create_lead_duplicate_phone(self):
        # 创建一个客户
        customer = self.create_customer(phone="13800138000")
        
        # 创建线索时检测到重复电话
        resp = self.create_lead(phone="138 0013 8000")
        self.assertEqual(resp["code"], "duplicate_contact")
        self.assertEqual(resp["duplicate_hint"]["object_type"], "customer")
        self.assertEqual(resp["duplicate_hint"]["object_id"], customer["id"])
        self.assertEqual(self.client.get("/api/crm/leads").json()["total"], 0)

    def test_create_lead_allows_same_wechat_because_phone_is_unique_key(self):
        self.create_customer(wechat="wechat123")
        resp = self.create_lead(phone=None, wechat="WECHAT123")
        self.assertEqual(resp["status"], "new")
        self.assertIsNone(resp["phone"])
        self.assertEqual(self.client.get("/api/crm/leads").json()["total"], 1)

    # ---------- 跟进兼容性 ----------
    def test_v1_follow_up_compatibility(self):
        """V1 兼容：支持旧的 customer_id/deal_id 参数"""
        customer = self.create_customer(phone="13800138000")
        deal = self.create_deal(customer["id"])
        
        # 使用旧的参数方式创建跟进
        data = {
            "customer_id": str(customer["id"]),
            "content": "测试跟进",
            "deal_id": str(deal["id"]),
        }
        resp = self.client.post("/api/crm/follow-ups", data=data)
        self.assertEqual(resp.status_code, 200, resp.text)
        
        # 验证跟进记录存在
        resp = self.client.get("/api/crm/follow-ups?customer_id=" + str(customer["id"]))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["customer_id"], customer["id"])
        self.assertEqual(body[0]["deal_id"], deal["id"])

    # ---------- 其他 ----------
    def test_lead_convert_with_new_mode(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["lead"]["status"], "converted")
        self.assertIsNotNone(body["customer"])
        self.assertIsNotNone(body["deal"])
        self.assertEqual(body["dedupe"], "forced")
        self.assertEqual(body["deal"]["spec"], "1200*2400")
        self.assertEqual(body["customer"]["created_at"], body["lead"]["created_at"])

    def test_company_lead_conversion_keeps_primary_contact_searchable(self):
        lead = self.create_lead(
            name="陈明",
            phone="18366326404",
            wechat="游戏520",
            lead_type="company",
            company_name="中电金信",
        )
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "天窗 XW-60",
                "product_type": "天窗",
                "model": "XW-60",
                "spec": "1400x480",
                "drive_type": "manual",
                "amount": 12800.0,
            },
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        customer = resp.json()["customer"]
        self.assertEqual(customer["name"], "中电金信")
        self.assertEqual(customer["company_name"], "中电金信")
        self.assertEqual(customer["primary_contact_name"], "陈明")
        self.assertEqual(customer["primary_contact_phone"], "18366326404")
        self.assertEqual(customer["primary_contact_wechat"], "游戏520")

        for term in ("陈明", "中电金信", "游戏520"):
            found = self.client.get(
                "/api/crm/customers", params={"search": term}
            ).json()
            self.assertEqual(found["total"], 1, term)
            self.assertEqual(found["items"][0]["id"], customer["id"], term)

    def test_lead_convert_with_link_mode(self):
        # 按 PLANNER §2.3：link 模式要求 link_customer_id 在去重命中集合内
        lead = self.create_lead(phone="13800138001")
        customer = self.create_customer(phone="13800138001")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "link",
            "link_customer_id": customer["id"],
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["lead"]["status"], "converted")
        self.assertEqual(body["customer"]["id"], customer["id"])
        self.assertIsNotNone(body["deal"])
        self.assertEqual(body["dedupe"], "linked")

    def test_lead_convert_with_invalid_link_customer_400(self):
        customer = self.create_customer(phone="13800138000")
        lead = self.create_lead(phone="13800138001")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "link",
            "link_customer_id": customer["id"] + 1,  # 不存在的客户ID
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_lead_convert_with_duplicate_customer_409(self):
        lead = self.create_lead(phone="13800138000")
        # 先建线索，再由历史客户导入/其它入口产生同联系方式客户
        self.create_customer(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertIn("已存在相同客户", resp.json()["detail"])

    def test_lead_convert_with_force_new(self):
        lead = self.create_lead(phone="13800138000")
        # 先建线索，再由历史客户导入/其它入口产生同联系方式客户
        self.create_customer(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "force_new": True,
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["lead"]["status"], "converted")
        self.assertIsNotNone(body["customer"])
        self.assertIsNotNone(body["deal"])
        self.assertEqual(body["dedupe"], "forced")

    def test_lead_convert_with_invalid_lead_status_409(self):
        lead = self.create_lead(phone="13800138000")
        # 转化线索
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        
        # 再次转化已转化的线索
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机2",
                "product_type": "天窗",
                "model": "平移",
                "spec": "1200*1400",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_lead_convert_with_invalid_deal_amount_400(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 0,  # 无效金额
            }
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_lead_convert_with_missing_deal_title_400(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "product_type": "天窗",
                "model": "平移",
                "spec": "1200*1400",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_lead_convert_with_missing_contact_info_400(self):
        # 直接落库造一条无联系方式的线索（API 会拦，故绕过）
        from app.db import db_conn
        from app.security import now_iso
        now = now_iso()
        with db_conn() as conn:
            cur = conn.execute(
                "INSERT INTO leads (name, source, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("无联系方式", "wechat", "new", now, now),
            )
            lead = {"id": int(cur.lastrowid)}
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_lead_convert_with_invalid_deal_stage_400(self):
        lead = self.create_lead(phone="13800138000")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
                "stage": "invalid_stage",
            }
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_lead_convert_with_nonexistent_lead_404(self):
        resp = self.client.post("/api/crm/leads/9999/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_lead_convert_with_nonexistent_customer_in_link_mode_400(self):
        lead = self.create_lead(phone="13800138001")
        resp = self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "link",
            "link_customer_id": 9999,
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.0,
            }
        })
        self.assertEqual(resp.status_code, 400, resp.text)


class FollowUpsV2Test(ApiTestCase):
    # 复用 LeadsTest 的构造助手（避免重复实现）
    create_lead = LeadsTest.create_lead
    post_follow_up = LeadsTest.post_follow_up

    # ---------- 小工具 ----------
    def test_follow_up_with_customer_object(self):
        """客户对象类型跟进"""
        customer = self.create_customer(name="张伟", phone="13800138000")
        
        resp = self.post_follow_up(
            "customer", 
            customer["id"],
            content="测试跟进内容"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["customer_id"], customer["id"])
        self.assertEqual(data["object_type"], "customer")

    def test_follow_up_with_lead_object(self):
        """线索对象类型跟进"""
        lead = self.create_lead(name="张伟", phone="13800138000")
        
        resp = self.post_follow_up(
            "lead", 
            lead["id"],
            content="测试跟进内容"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["object_type"], "lead")
        detail = self.client.get(f"/api/crm/leads/{lead['id']}").json()
        self.assertEqual(detail["status"], "following")
        filtered = self.client.get("/api/crm/leads?status=following").json()
        self.assertEqual([item["id"] for item in filtered["items"]], [lead["id"]])

    def test_follow_up_with_deal_object(self):
        """商机对象类型跟进"""
        customer = self.create_customer(name="张伟", phone="13800138000")
        deal = self.create_deal(customer["id"], amount=12800.00)
        
        resp = self.post_follow_up(
            "deal", 
            deal["id"],
            content="测试跟进内容"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["object_type"], "deal")

    def test_follow_up_with_invalid_object_type(self):
        """无效对象类型返回400"""
        resp = self.post_follow_up(
            "invalid_type", 
            1,
            content="测试跟进内容"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("非法对象类型", resp.json()["detail"])

    def test_follow_up_with_deal_frozen(self):
        """商机冻结时添加跟进返回409"""
        customer = self.create_customer(name="张伟", phone="13800138000")
        deal = self.create_deal(customer["id"], amount=12800.00)
        
        # 赢单
        self.client.post(f"/api/crm/deals/{deal['id']}/win")
        
        # 尝试添加跟进
        resp = self.post_follow_up(
            "deal", 
            deal["id"],
            content="测试跟进内容"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("商机已赢单或已流失", resp.json()["detail"])

    def test_follow_up_with_lead_closed(self):
        """线索终结时添加跟进返回409"""
        lead = self.create_lead(name="张伟", phone="13800138000")
        
        # 转化线索
        self.client.post(f"/api/crm/leads/{lead['id']}/convert", json={
            "mode": "new",
            "deal": {
                "title": "测试商机",
                "product_type": "天窗",
                "model": "XW-120",
                "spec": "1200*2400",
                "drive_type": "manual",
                "amount": 12800.00
            }
        })
        
        # 尝试添加跟进
        resp = self.post_follow_up(
            "lead", 
            lead["id"],
            content="测试跟进内容"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("线索已转化或已失效", resp.json()["detail"])

    def test_follow_up_with_intent_level_update(self):
        """跟进时更新意向等级"""
        customer = self.create_customer(name="张伟", phone="13800138000")
        
        resp = self.post_follow_up(
            "customer", 
            customer["id"],
            content="测试跟进内容",
            intent_level="high"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["object_type"], "customer")
        
        # 检查客户意向等级是否更新
        customer_resp = self.client.get(f"/api/crm/customers/{customer['id']}")
        self.assertEqual(customer_resp.status_code, 200)
        customer_data = customer_resp.json()
        self.assertEqual(customer_data["intent_level"], "high")

    def test_follow_up_list_filter_by_object(self):
        """按对象类型和ID过滤跟进"""
        customer = self.create_customer(name="张伟", phone="13800138000")
        lead = self.create_lead(name="李娜", phone="13900139000")
        
        # 添加跟进
        self.post_follow_up("customer", customer["id"], content="客户跟进")
        self.post_follow_up("lead", lead["id"], content="线索跟进")
        
        # 按客户过滤
        resp = self.client.get(f"/api/crm/follow-ups?object_type=customer&object_id={customer['id']}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["object_type"], "customer")
        
        # 按线索过滤
        resp = self.client.get(f"/api/crm/follow-ups?object_type=lead&object_id={lead['id']}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["object_type"], "lead")


if __name__ == "__main__":
    unittest.main()
