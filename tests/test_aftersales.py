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

    def test_start_aftersale(self):
        """测试开始处理售后单"""
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

        # 开始处理
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "processing")

    def test_start_aftersale_invalid_status(self):
        """测试开始处理售后单状态不正确"""
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

        # 开始处理
        self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        
        # 再次尝试开始处理（状态已经是processing）
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        self.assertEqual(resp.status_code, 409)

    def test_finish_aftersale(self):
        """测试完成售后单"""
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

        # 开始处理
        self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        
        # 完成处理
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish",
            json={"result": "已修复"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["result"], "已修复")

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

        # 开始处理
        self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        
        # 完成处理但没有结果
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish",
            json={"result": ""}
        )
        self.assertEqual(resp.status_code, 400)

    def test_reject_aftersale(self):
        """测试拒绝售后单"""
        # 先创建售后单
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

        # 拒绝售后单
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/reject",
            json={"reject_reason": "客户自己弄坏了"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["reject_reason"], "客户自己弄坏了")

    def test_reject_aftersale_missing_reason(self):
        """测试拒绝售后单缺少拒绝原因"""
        # 先创建售后单
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

        # 拒绝售后单但没有原因
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/reject",
            json={"reject_reason": ""}
        )
        self.assertEqual(resp.status_code, 400)

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

        # 开始处理
        self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        
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
        """测试售后单完成后不能再操作"""
        # 创建并完成售后单
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

        # 开始处理
        self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        
        # 完成处理
        self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish",
            json={"result": "已修复"}
        )

        # 再次尝试开始处理（应该失败）
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        self.assertEqual(resp.status_code, 409)

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