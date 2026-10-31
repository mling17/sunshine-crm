"""
售后单功能测试
"""
import unittest
from unittest.mock import patch, MagicMock

from tests._util import ApiTestCase, insert_customer, insert_order


class TestAftersales(ApiTestCase):
    def setUp(self):
        super().setUp()
        # 初始化一些测试数据
        self.customer = insert_customer(name="测试客户")
        self.order = insert_order(
            customer_id=self.customer["id"],
            amount=1000.0,
            status="completed"
        )

    def _create_aftersale(self) -> int:
        resp = self.client.post(
            "/api/crm/aftersales",
            json={"order_id": self.order["id"], "type": "repair",
                  "description": "产品有质量问题"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["id"]

    def test_create_aftersale(self):
        """测试创建售后单"""
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["type"], "repair")
        self.assertIn("AS-", data["no"])

    def test_create_aftersale_not_found_order(self):
        """测试创建售后单时订单不存在"""
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": 99999,
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 404)

    def test_get_aftersale_detail(self):
        """测试获取售后单详情"""
        # 先创建一个售后单
        aftersale_resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(aftersale_resp.status_code, 200)
        aftersale_data = aftersale_resp.json()
        aftersale_id = aftersale_data["id"]

        # 获取详情
        resp = self.client.get(f"/api/crm/aftersales/{aftersale_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], aftersale_id)
        self.assertEqual(data["type"], "repair")

    def test_start_aftersale_deprecated(self):
        """定稿：不再有「开始处理」，接口返回 410（记跟进自动进入处理中）"""
        aftersale_id = self._create_aftersale()
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        self.assertEqual(resp.status_code, 410, resp.text)
        self.assertEqual(resp.json()["code"], "deprecated")

    def test_follow_up_moves_aftersale_to_processing(self):
        """记一条跟进 → 待处理自动变处理中（定稿 v2.4 #9）"""
        aftersale_id = self._create_aftersale()
        fu = self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id),
                  "content": "已上门检查，等配件"},
        )
        self.assertEqual(fu.status_code, 200, fu.text)
        detail = self.client.get(f"/api/crm/aftersales/{aftersale_id}").json()
        self.assertEqual(detail["status"], "processing")
        types = [t["type"] for t in detail.get("timeline", [])]
        self.assertIn("follow", types)

    def test_finish_aftersale(self):
        """先记跟进（自动处理中）→ 标记完成 → 写 result/closed_at + 履历"""
        aftersale_id = self._create_aftersale()
        pending_finish = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已修复"}
        )
        self.assertEqual(pending_finish.status_code, 409, "待处理不能直接完成")
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id),
                  "content": "已上门更换电机"},
        )
        done = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已修复"}
        )
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["status"], "done")
        self.assertTrue(done.json()["closed_at"])

    def test_finish_aftersale_missing_result(self):
        """测试完成售后单缺少处理结果"""
        # 先创建并开始处理售后单
        aftersale_resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(aftersale_resp.status_code, 200)
        aftersale_data = aftersale_resp.json()
        aftersale_id = aftersale_data["id"]

        # 定稿：记一条跟进 → 自动进入处理中
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "开始处理"},
        )
        
        # 完成处理但没有结果
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish",
            json={"result": ""}
        )
        self.assertEqual(resp.status_code, 400)

    def test_reject_aftersale_deprecated(self):
        """定稿：售后不再支持拒绝，接口 410"""
        aftersale_id = self._create_aftersale()
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/reject", json={"reject_reason": "不属于售后范围"}
        )
        self.assertEqual(resp.status_code, 410, resp.text)

    def test_reject_without_reason_also_deprecated(self):
        aftersale_id = self._create_aftersale()
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/reject", json={})
        self.assertEqual(resp.status_code, 410, resp.text)

    def test_list_aftersales(self):
        """测试获取售后单列表"""
        # 创建几个售后单
        self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "return",
                "description": "想要退货"
            }
        )

        # 获取列表
        resp = self.client.get("/api/crm/aftersales")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 2)

    def test_list_aftersales_filter_by_status(self):
        """测试按状态筛选售后单列表"""
        # 创建一个售后单
        aftersale_resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(aftersale_resp.status_code, 200)
        aftersale_data = aftersale_resp.json()
        aftersale_id = aftersale_data["id"]

        # 定稿：记一条跟进 → 自动进入处理中
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "开始处理"},
        )
        
        # 获取待处理的售后单
        resp = self.client.get("/api/crm/aftersales?status=pending")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 应该没有待处理的单
        self.assertEqual(data["total"], 0)

        # 获取处理中的售后单
        resp = self.client.get("/api/crm/aftersales?status=processing")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 应该有一个处理中的单
        self.assertEqual(data["total"], 1)

    def test_aftersale_closed_after_done(self):
        """完成后再记跟进 → 409 aftersale_closed（定稿 v2.6 #3）"""
        aftersale_id = self._create_aftersale()
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "处理中"},
        )
        self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已修复"}
        )
        resp = self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "再来一条"},
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "aftersale_closed")

    def test_aftersale_sla_boundary(self):
        """测试售后单SLA边界条件"""
        # 创建售后单
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        aftersale_id = data["id"]
        
        # 检查售后单是否在待处理状态
        resp = self.client.get(f"/api/crm/aftersales/{aftersale_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "pending")


if __name__ == "__main__":
    unittest.main()