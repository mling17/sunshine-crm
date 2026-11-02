"""统计 8 块 + 工作台卡片 + 线索派生字段（PLANNER-V3 §5.2 / §5.3 / §5.9）。"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from tests._util import ApiTestCase


class StatsTest(ApiTestCase):
    def _win_deal(self, deal_id: int) -> None:
        result = self.client.post(f"/api/crm/deals/{deal_id}/win")
        self.assertEqual(result.status_code, 200, result.text)
        order_id = result.json()["order"]["id"]
        confirmed = self.client.post(
            f"/api/crm/orders/{order_id}/confirm",
            data={"note": "统计测试客户已确认"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

    def _seed(self):
        c = self.create_customer(name="老客甲", source="wechat")
        d1 = self.create_deal(c["id"], amount=1000.0, drive_type="manual")
        d2 = self.create_deal(c["id"], amount=2000.0, drive_type="electric")
        self.client.put(f"/api/crm/deals/{d2['id']}", json={"stage": "confirm"})
        c2 = self.create_customer(name="新客乙", source="referral")
        d3 = self.create_deal(c2["id"], amount=5000.0, drive_type="manual")
        self._win_deal(d3["id"])
        d4 = self.create_deal(c2["id"], amount=3000.0, drive_type="manual")
        self.client.post(f"/api/crm/deals/{d4['id']}/lose", json={"lost_reason": "price"})
        return c, c2

    def test_stats_has_eight_blocks(self):
        self._seed()
        data = self.client.get("/api/crm/stats").json()
        for key in (
            "kpis",
            "months",
            "funnel",
            "lead_conversion",
            "deals_by_stage",
            "orders_by_status",
            "customer_sources",
            "aftersale_types",
        ):
            self.assertIn(key, data, f"统计缺 {key}")
        self.assertEqual(len(data["months"]), 6, "默认近 6 个月")
        keys = [m["key"] for m in data["months"]]
        self.assertEqual(len(set(keys)), 6, "6 个月份不能重复（10-31 减月的进位坑）")
        self.assertEqual(keys, sorted(keys), "月份要按时间正序")
        self.assertEqual(len(data["orders_by_status"]), 8, "8 个订单状态都要给")

    def test_funnel_is_cumulative_and_ignores_lost(self):
        self._seed()
        funnel = {i["key"]: i["value"] for i in self.client.get("/api/crm/stats").json()["funnel"]}
        # quote 1 + confirm 1 + won 1 = 3（lost 不计）
        self.assertEqual(funnel["quote"], 3)
        self.assertEqual(funnel["confirm"], 2)
        self.assertEqual(funnel["won"], 1)

    def test_lead_conversion_never_over_100(self):
        c = self.create_customer(name="来源客户")
        lead = self.client.post(
            "/api/crm/leads", json={"name": "韩雪", "phone": "18753112299", "source": "referral"}
        ).json()
        conv = self.client.post(
            f"/api/crm/leads/{lead['id']}/convert",
            json={"mode": "new", "deal": {"amount": 100.0, "drive_type": "manual",
                                          "product_type": "天窗", "model": "XW-90"}},
        )
        self.assertEqual(conv.status_code, 200, conv.text)
        conv = self.client.get("/api/crm/stats").json()["lead_conversion"]
        self.assertLessEqual(conv["rate"], 100.0)
        self.assertEqual(conv["total"], 1)
        self.assertEqual(conv["converted"], 1)

    def test_kpis_reflect_data(self):
        self._seed()
        kpis = self.client.get("/api/crm/stats").json()["kpis"]
        self.assertEqual(kpis["customers_total"], 2)
        self.assertEqual(kpis["active_deals"], 2, "进行中 = quote1 + confirm1")
        self.assertEqual(kpis["repeat_customers"], 2, "老客甲、新客乙各有 2 单")
        self.assertEqual(kpis["month_won"]["count"], 1)

    def test_source_distribution(self):
        self._seed()
        sources = self.client.get("/api/crm/stats").json()["customer_sources"]
        self.assertEqual({s["key"] for s in sources}, {"wechat", "referral"})
        self.assertEqual(sum(s["value"] for s in sources), 2)

    def test_7d_range_uses_seven_local_days_and_filters_cohort(self):
        self.client.post(
            "/api/crm/leads",
            json={"name": "近七天线索", "phone": "18753110001", "source": "wechat"},
        )
        old_day = (date.today() - timedelta(days=8)).isoformat() + "T08:00:00Z"
        with self.db_conn() as conn:
            conn.execute(
                """
                INSERT INTO leads
                    (name, phone, source, status, created_at, updated_at)
                VALUES (?, ?, ?, 'new', ?, ?)
                """,
                ("区间外线索", "18753110002", "phone", old_day, old_day),
            )

        data = self.client.get("/api/crm/stats?range=7d").json()
        expected_start = (date.today() - timedelta(days=6)).isoformat()
        self.assertEqual(data["range"]["key"], "7d")
        self.assertEqual(data["range"]["label"], "近7天")
        self.assertEqual(data["range"]["start"], expected_start)
        self.assertEqual(data["summary"]["newLeads"], 1)
        self.assertEqual(data["range"]["end"], date.today().isoformat())
        self.assertEqual(len(data["months"]), 7)
        self.assertEqual(len(data["trend"]["labels"]), 7)
        self.assertEqual(len(data["lead_funnel"]), 5)
        self.assertIn("products", data)
        self.assertIn("sources", data)
        self.assertIn("service_status", data)

    def test_period_alias_is_backwards_compatible(self):
        data = self.client.get("/api/crm/stats?period=3m").json()
        self.assertEqual(data["range"]["key"], "3m")
        self.assertEqual(data["range"]["label"], "近3月")
        self.assertEqual(len(data["months"]), 3)


class WorkbenchTest(ApiTestCase):
    def test_in_progress_and_recent_activities(self):
        c = self.create_customer(name="张三")
        d = self.create_deal(c["id"], amount=4000.0, drive_type="manual")
        self.add_follow_up(c["id"], content="今天电话沟通", next_date=None, deal_id=d["id"])

        stats = self.dashboard()["stats"]
        self.assertEqual(stats["in_progress_deals"]["count"], 1)
        self.assertEqual(stats["in_progress_deals"]["amount"], 4000.0)
        self.assertTrue(stats["recent_activities"], "最近动态不能为空")
        self.assertEqual(stats["recent_activities"][0]["type"], "follow")

    def test_order_event_appears_in_activities(self):
        c = self.create_customer(name="李四")
        d = self.create_deal(c["id"], amount=9000.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{d['id']}", json={"stage": "confirm"})
        order = self.client.post(
            f"/api/crm/deals/{d['id']}/orders",
            json={"deposit": 2000, "logistics_mode": "self"},
        ).json()["order"]
        self.client.post(
            f"/api/crm/orders/{order['id']}/confirm",
            data={"note": "工作台测试客户已确认"},
        )
        self.client.post(f"/api/crm/orders/{order['id']}/pay-deposit", data={"amount": "2000"})

        acts = self.dashboard()["stats"]["recent_activities"]
        self.assertIn("pay", [a["type"] for a in acts])
        self.assertTrue(any("定金" in a["text"] for a in acts))

    def test_dashboard_adds_yesterday_summary_and_recent_services(self):
        stats = self.dashboard()["stats"]
        self.assertEqual(
            {item["key"] for item in stats["yesterday_activity"]},
            {"lead", "customer", "deal", "order", "aftersale"},
        )
        self.assertTrue(all(
            {"new_count", "followups"} <= set(item)
            for item in stats["yesterday_activity"]
        ))
        self.assertEqual(stats["recent_aftersales"], [])


class LeadDerivedTest(ApiTestCase):
    def test_lead_list_has_last_follow_and_overdue(self):
        lead = self.client.post(
            "/api/crm/leads", json={"name": "韩雪", "phone": "18753112299", "source": "wechat"}
        ).json()
        self.assertIsNone(lead.get("last_follow_at"))
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "lead", "object_id": str(lead["id"]),
                  "content": "聊了需求", "next_date": "2026-10-29"},
        )
        rows = self.client.get("/api/crm/leads").json()["items"]
        target = [r for r in rows if r["id"] == lead["id"]][0]
        self.assertIsNotNone(target["last_follow_at"])
        self.assertEqual(target["next_date"], "2026-10-29")
        self.assertGreaterEqual(target["days_overdue"], 1, "过约定日期要能算出逾期天数")

    def test_lead_default_intent_is_medium(self):
        lead = self.client.post(
            "/api/crm/leads", json={"name": "徐婷", "phone": "15905313344", "source": "wechat"}
        ).json()
        self.assertEqual(lead["intent_level"], "medium")
        self.assertEqual(lead["intent_level_label"], "中")


if __name__ == "__main__":
    unittest.main()
