"""订单模块测试"""
import unittest
from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import，设定临时 DB/上传目录
from tests._util import ApiTestCase, db_conn


class OrdersTest(ApiTestCase):
    def test_create_order_should_fail(self):
        """测试不能直接创建订单"""
        response = self.client.post("/api/crm/orders", json={
            "customer_id": 1,
            "deal_id": 1,
            "amount": 1000.0,
            "status": "pending_payment"
        })
        # 由于路由不存在，返回 404
        self.assertEqual(response.status_code, 404)

    def test_get_order(self):
        """测试获取订单详情"""
        # 先创建一个订单用于测试
        with self.db_conn() as conn:
            # 创建测试订单
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-001",
                    1,
                    1,
                    "产品类型",
                    "型号",
                    "规格",
                    1000.0,
                    "pending_payment",
                    "测试人员",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 测试获取订单
            response = self.client.get(f"/api/crm/orders/{order_id}")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["id"], order_id)
            self.assertEqual(data["order_no"], "SO-20261030-001")
            self.assertEqual(data["amount"], 1000.0)
            self.assertEqual(data["status"], "pending_payment")
            
            # 清理测试数据
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    def test_list_orders(self):
        """测试订单列表"""
        # 先创建几个测试订单
        with self.db_conn() as conn:
            # 创建测试订单1
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-001",
                    1,
                    1,
                    "产品类型",
                    "型号",
                    "规格",
                    1000.0,
                    "pending_payment",
                    "测试人员",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 创建测试订单2
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-002",
                    2,
                    2,
                    "产品类型2",
                    "型号2",
                    "规格2",
                    2000.0,
                    "deposit_paid",
                    "测试人员2",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 测试获取订单列表
            response = self.client.get("/api/crm/orders")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertGreaterEqual(len(data), 2)
            
            # 测试按客户筛选
            response = self.client.get("/api/crm/orders?customer_id=1")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertGreaterEqual(len(data), 1)
            
            # 测试按状态筛选
            response = self.client.get("/api/crm/orders?status=pending_payment")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertGreaterEqual(len(data), 1)
            
            # 清理测试数据
            conn.execute("DELETE FROM orders WHERE id IN (?, ?)", (order_id1, order_id2))

    def test_order_transition(self):
        """测试订单状态转换"""
        with self.db_conn() as conn:
            # 创建测试订单
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-001",
                    1,
                    1,
                    "产品类型",
                    "型号",
                    "规格",
                    1000.0,
                    "pending_payment",
                    "测试人员",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 测试支付押金
            response = self.client.post(f"/api/crm/orders/{order_id}/transition", json={
                "to_status": "deposit_paid",
                "deposit": 300.0,
                "note": "支付押金"
            })
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["order"]["status"], "deposit_paid")
            self.assertEqual(data["order"]["paid_amount"], 300.0)
            
            # 测试支付尾款
            response = self.client.post(f"/api/crm/orders/{order_id}/transition", json={
                "to_status": "balance_paid",
                "balance": 700.0,
                "note": "支付尾款"
            })
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["order"]["status"], "balance_paid")
            self.assertEqual(data["order"]["paid_amount"], 1000.0)
            
            # 清理测试数据
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    def test_invalid_transition(self):
        """测试无效状态转换"""
        with self.db_conn() as conn:
            # 创建测试订单
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-001",
                    1,
                    1,
                    "产品类型",
                    "型号",
                    "规格",
                    1000.0,
                    "pending_payment",
                    "测试人员",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 测试无效的转换
            response = self.client.post(f"/api/crm/orders/{order_id}/transition", json={
                "to_status": "shipped",
                "note": "直接跳转到发货"
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("不能流转到", response.json()["detail"])
            
            # 清理测试数据
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    def test_q1_balance_validation(self):
        """测试Q1尾款校验"""
        with self.db_conn() as conn:
            # 创建测试订单
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-001",
                    1,
                    1,
                    "产品类型",
                    "型号",
                    "规格",
                    1000.0,
                    "pending_payment",
                    "测试人员",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 先支付押金
            response = self.client.post(f"/api/crm/orders/{order_id}/transition", json={
                "to_status": "deposit_paid",
                "deposit": 300.0,
                "note": "支付押金"
            })
            self.assertEqual(response.status_code, 200)
            
            # 测试尾款金额不匹配的情况
            response = self.client.post(f"/api/crm/orders/{order_id}/transition", json={
                "to_status": "balance_paid",
                "balance": 600.0,  # 应该是700元
                "note": "支付尾款"
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("尾款应为", response.json()["detail"])
            
            # 清理测试数据
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    def test_carrier_delete_protection(self):
        """测试物流公司删除保护(Q7)"""
        with db_conn() as conn:
            # 创建测试物流公司
            conn.execute(
                """
                INSERT INTO carriers 
                    (name, code, contact_person, phone, address, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "测试物流公司",
                    "TEST001",
                    "测试联系人",
                    "13800138000",
                    "测试地址",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            carrier_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 创建测试订单并关联物流公司
            conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, carrier_id, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SO-20261030-001",
                    1,
                    1,
                    "产品类型",
                    "型号",
                    "规格",
                    1000.0,
                    "ready_to_ship",
                    carrier_id,
                    "测试人员",
                    "2026-10-30T10:00:00Z",
                    "2026-10-30T10:00:00Z",
                ),
            )
            order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # 尝试删除被引用的物流公司
            response = self.client.delete(f"/api/crm/carriers/{carrier_id}")
            self.assertEqual(response.status_code, 409)
            self.assertIn("已被订单引用", response.json()["message"])
            
            # 清理测试数据
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            conn.execute("DELETE FROM carriers WHERE id = ?", (carrier_id,))

    def test_carrier_delete_allowed(self):
        """测试未被引用的物流公司可以删除"""
        # 创建一个物流公司
        carrier_response = self.client.post("/api/crm/carriers", json={
            "name": "测试物流2",
            "code": "TEST002"
        })
        self.assertEqual(carrier_response.status_code, 200)
        carrier_data = carrier_response.json()
        carrier_id = carrier_data["id"]
        
        # 删除未被引用的物流公司，应该返回 200
        response = self.client.delete(f"/api/crm/carriers/{carrier_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "删除成功")
        
        # 清理测试数据
        with db_conn() as conn:
            conn.execute("DELETE FROM carriers WHERE id = ?", (carrier_id,))


if __name__ == "__main__":
    unittest.main()