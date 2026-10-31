"""物流公司模块测试"""
import unittest
from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import，设定临时 DB/上传目录
from tests._util import ApiTestCase, db_conn


class CarriersTest(ApiTestCase):
    def test_create_carrier(self):
        """测试创建物流公司"""
        response = self.client.post("/api/crm/carriers", json={
            "name": "顺丰快递",
            "code": "SF",
            "contact_person": "张三",
            "phone": "13800138000",
            "address": "北京市朝阳区"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "顺丰快递")
        self.assertEqual(data["code"], "SF")
        
        # 清理测试数据
        carrier_id = data["id"]
        self.client.delete(f"/api/crm/carriers/{carrier_id}")

    def test_list_carriers(self):
        """测试获取物流公司列表"""
        response = self.client.get("/api/crm/carriers")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_get_carrier(self):
        """测试获取物流公司详情"""
        # 先创建一个物流公司
        response = self.client.post("/api/crm/carriers", json={
            "name": "圆通快递",
            "code": "YT",
            "contact_person": "李四",
            "phone": "13900139000",
            "address": "上海市浦东新区"
        })
        self.assertEqual(response.status_code, 200)
        carrier_data = response.json()
        carrier_id = carrier_data["id"]
        
        # 获取详情
        response = self.client.get(f"/api/crm/carriers/{carrier_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "圆通快递")
        self.assertEqual(data["code"], "YT")
        
        # 清理测试数据
        self.client.delete(f"/api/crm/carriers/{carrier_id}")

    def test_update_carrier(self):
        """测试更新物流公司"""
        # 先创建一个物流公司
        response = self.client.post("/api/crm/carriers", json={
            "name": "中通快递",
            "code": "ZT",
            "contact_person": "王五",
            "phone": "13700137000",
            "address": "广州市天河区"
        })
        self.assertEqual(response.status_code, 200)
        carrier_data = response.json()
        carrier_id = carrier_data["id"]
        
        # 更新信息
        response = self.client.put(f"/api/crm/carriers/{carrier_id}", json={
            "name": "中通快递(更新)",
            "code": "ZT2",
            "contact_person": "赵六",
            "phone": "13600136000",
            "address": "深圳市南山区"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "中通快递(更新)")
        self.assertEqual(data["code"], "ZT2")
        
        # 清理测试数据
        self.client.delete(f"/api/crm/carriers/{carrier_id}")

    def test_carrier_delete_referenced(self):
        """测试删除被引用的物流公司应该返回 409"""
        # 创建一个物流公司
        carrier_response = self.client.post("/api/crm/carriers", json={
            "name": "测试物流",
            "code": "TEST001"
        })
        self.assertEqual(carrier_response.status_code, 200)
        carrier_data = carrier_response.json()
        carrier_id = carrier_data["id"]
        
        # 创建一个订单并关联该物流公司
        with db_conn() as conn:
            # 先插入一个测试客户
            conn.execute(
                "INSERT INTO customers (name, created_at, updated_at) VALUES (?, ?, ?)",
                ("测试客户", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )
            customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 订单必须挂在真实商机上（1:1 + 外键）
            conn.execute(
                "INSERT INTO deals (customer_id, amount, stage, created_at, updated_at)"
                " VALUES (?, ?, 'won', ?, ?)",
                (customer_id, 1000.0, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )
            deal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 插入一个测试订单
            conn.execute(
                """
                INSERT INTO orders (order_no, customer_id, deal_id, amount, status, 
                                  carrier_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("SO-20260101-001", customer_id, deal_id, 1000.0, "pending_payment", 
                 carrier_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )
        
        # 尝试删除被引用的物流公司，应该返回 409
        response = self.client.delete(f"/api/crm/carriers/{carrier_id}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "carrier_in_use")  # 计划 §2.6 错误码
        
        # 清理测试数据
        with db_conn() as conn:
            # 删除订单
            conn.execute("DELETE FROM orders WHERE carrier_id = ?", (carrier_id,))
            # 删除物流公司
            conn.execute("DELETE FROM carriers WHERE id = ?", (carrier_id,))

    def test_carrier_delete_not_referenced(self):
        """测试删除未被引用的物流公司应该成功"""
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


if __name__ == "__main__":
    unittest.main()