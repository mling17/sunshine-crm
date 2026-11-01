"""
工作台功能测试
"""
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from tests._util import ApiTestCase, insert_customer, insert_order, insert_deal


class TestWorkbench(ApiTestCase):
    def setUp(self):
        super().setUp()
        # 初始化一些测试数据
        self.customer = insert_customer(name="测试客户")
        # 注意：setUp 不预置订单，避免污染「订单状态统计/最近订单」的计数断言

    def test_dashboard_orders_by_status(self):
        """测试工作台订单状态统计"""
        # 创建不同状态的订单
        insert_order(customer_id=self.customer["id"], amount=500.0, status="pending_payment")
        insert_order(customer_id=self.customer["id"], amount=600.0, status="deposit_paid")
        insert_order(customer_id=self.customer["id"], amount=700.0, status="completed")
        
        resp = self.client.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查订单状态统计
        orders_by_status = data["stats"]["orders_by_status"]
        self.assertIn("pending_payment", orders_by_status)
        self.assertIn("deposit_paid", orders_by_status)
        self.assertIn("completed", orders_by_status)
        
        # 检查状态计数
        self.assertEqual(orders_by_status["pending_payment"]["count"], 1)
        self.assertEqual(orders_by_status["deposit_paid"]["count"], 1)
        self.assertEqual(orders_by_status["completed"]["count"], 1)
        
        # 检查金额
        self.assertEqual(orders_by_status["pending_payment"]["amount"], 500.0)
        self.assertEqual(orders_by_status["deposit_paid"]["amount"], 600.0)
        self.assertEqual(orders_by_status["completed"]["amount"], 700.0)

    def test_dashboard_recent_orders(self):
        """测试工作台最近订单"""
        # 创建订单
        order1 = insert_order(customer_id=self.customer["id"], amount=500.0, status="completed")
        order2 = insert_order(customer_id=self.customer["id"], amount=600.0, status="shipped")
        
        resp = self.client.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查最近订单
        recent_orders = data["stats"]["recent_orders"]
        self.assertEqual(len(recent_orders), 2)
        
        # 检查订单字段
        order_ids = [o["id"] for o in recent_orders]
        self.assertIn(order1["id"], order_ids)
        self.assertIn(order2["id"], order_ids)
        
        # 检查订单金额和状态
        for order in recent_orders:
            if order["id"] == order1["id"]:
                self.assertEqual(order["amount"], 500.0)
                self.assertEqual(order["status"], "completed")
            elif order["id"] == order2["id"]:
                self.assertEqual(order["amount"], 600.0)
                self.assertEqual(order["status"], "shipped")

    def test_dashboard_sla_alerts(self):
        """测试工作台SLA告警"""
        order = insert_order(customer_id=self.customer["id"], amount=1000.0, status="completed")
        # 创建售后单
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 200)
        aftersale_data = resp.json()
        
        # 检查是否有SLA告警
        resp = self.client.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查售后单SLA告警
        sla_alerts = data["stats"]["aftersale_sla_alerts"]
        # 初始状态应该是空的，因为创建时间很近
        self.assertEqual(len(sla_alerts), 0)

    def test_dashboard_v1_compatibility(self):
        """测试V1工作台兼容性"""
        resp = self.client.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查V1兼容字段
        self.assertIn("today_followups", data)
        self.assertIn("month_won", data)
        self.assertIn("stats", data)
        
        # 检查stats中的V1字段
        stats = data["stats"]
        self.assertIn("customers_total", stats)
        self.assertIn("deals_by_stage", stats)
        self.assertIn("month_new_customers", stats)
        self.assertIn("repeat_customers", stats)
        self.assertIn("month_won", stats)
        
        # 检查新增字段
        self.assertIn("orders_by_status", stats)
        self.assertIn("recent_orders", stats)
        self.assertIn("aftersale_sla_alerts", stats)

    def test_dashboard_orders_by_status_all_zero(self):
        """测试订单状态统计全为0的情况"""
        resp = self.client.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # 检查订单状态统计
        orders_by_status = data["stats"]["orders_by_status"]
        # 检查所有 8 种状态都存在且计数为 0
        expected_statuses = [
            "pending_confirmation", "pending_payment", "deposit_paid", "producing",
            "balance_paid", "ready_to_ship", "shipped", "completed",
        ]
        for status in expected_statuses:
            self.assertIn(status, orders_by_status)
            self.assertEqual(orders_by_status[status]["count"], 0)
            self.assertEqual(orders_by_status[status]["amount"], 0.0)

    def test_dashboard_no_auth(self):
        """测试未认证访问工作台"""
        from tests._util import open_client
        
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        resp = anon.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
