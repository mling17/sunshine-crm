"""真实 MySQL 8 冒烟测试。

默认跳过。单独在专用测试库上执行：

    CRM_TEST_MYSQL=1 CRM_DB_ENGINE=mysql \
    CRM_MYSQL_HOST=127.0.0.1 CRM_MYSQL_USER=... CRM_MYSQL_PASSWORD=... \
    CRM_MYSQL_DATABASE=sunshine_crm_test \
    python -m unittest tests.test_mysql_live
"""

from __future__ import annotations

import os
import unittest
from datetime import date


LIVE = os.environ.get("CRM_TEST_MYSQL") == "1"


@unittest.skipUnless(LIVE, "设置 CRM_TEST_MYSQL=1 后运行真实 MySQL 测试")
class MySQLLiveSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("ADMIN_USERNAME", "mysql_test_admin")
        os.environ.setdefault("ADMIN_PASSWORD", "mysql-test-password")
        from fastapi.testclient import TestClient
        from app.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()
        response = cls.client.post(
            "/api/crm/login",
            json={
                "username": os.environ["ADMIN_USERNAME"],
                "password": os.environ["ADMIN_PASSWORD"],
            },
        )
        if response.status_code != 200:
            cls.client.__exit__(None, None, None)
            raise RuntimeError(f"MySQL 测试登录失败: {response.status_code} {response.text}")

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_reports_mysql(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["db_engine"], "mysql")
        self.assertNotIn(os.environ.get("CRM_MYSQL_PASSWORD", ""), body["db"])

    def test_write_dashboard_and_timeline(self):
        suffix = str(os.getpid())
        customer = self.client.post(
            "/api/crm/customers",
            json={
                "name": f"MySQL冒烟{suffix}",
                "phone": f"1390000{suffix[-4:]}",
                "source": "wechat",
            },
        )
        self.assertEqual(customer.status_code, 200, customer.text)
        customer_id = customer.json()["id"]

        deal = self.client.post(
            "/api/crm/deals",
            json={
                "customer_id": customer_id,
                "amount": 8800,
                "drive_type": "manual",
                "product_type": "天窗",
                "model": "XW-90",
            },
        )
        self.assertEqual(deal.status_code, 200, deal.text)
        deal_id = deal.json()["id"]

        follow = self.client.post(
            "/api/crm/follow-ups",
            data={
                "customer_id": str(customer_id),
                "deal_id": str(deal_id),
                "content": "MySQL 冒烟跟进",
                "next_date": date.today().isoformat(),
            },
        )
        self.assertEqual(follow.status_code, 200, follow.text)

        dashboard = self.client.get("/api/crm/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertTrue(
            any(item["content"] == "MySQL 冒烟跟进" for item in dashboard.json()["today_followups"])
        )

        detail = self.client.get(f"/api/crm/deals/{deal_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertTrue(detail.json()["timeline"])


if __name__ == "__main__":
    unittest.main()
