"""T6：首页看板 —— 今日待跟进（next_date ≤ 今天且未闭环）+ 本月成交 + 简单统计。

口径铁律：服务器 CST，"今天/本月"全部用 SQLite ``date('now','localtime')`` /
``'start of month'``，绝不用 UTC（否则跨零点待办会错一天）。
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import

from app.models import STAGES
from tests._util import ApiTestCase


def day(offset: int = 0) -> str:
    return (date.today() + timedelta(days=offset)).strftime("%Y-%m-%d")


def last_month_day() -> str:
    """上月 15 号（``YYYY-MM-15``），用来验证「本月成交」不会算进上月。"""
    first_this_month = datetime.now().replace(day=1)
    return (first_this_month - timedelta(days=1)).strftime("%Y-%m-15")


class DashboardTest(ApiTestCase):
    def _win_and_confirm_deal(self, deal_id: int) -> dict:
        result = self.client.post(f"/api/crm/deals/{deal_id}/win")
        self.assertEqual(result.status_code, 200, result.text)
        order_id = result.json()["order"]["id"]
        confirmed = self.client.post(
            f"/api/crm/orders/{order_id}/confirm",
            data={"note": "工作台统计测试客户已确认"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        return confirmed.json()

    def dashboard(self) -> dict:
        resp = self.client.get("/api/crm/dashboard")
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def add_follow_up(self, customer_id: int, *, content: str, next_date: str | None = None, deal_id: int | None = None) -> dict:
        data = {"customer_id": str(customer_id), "content": content}
        if next_date is not None:
            data["next_date"] = next_date
        if deal_id is not None:
            data["deal_id"] = str(deal_id)
        resp = self.client.post("/api/crm/follow-ups", data=data)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    # ---------- 今日待跟进 ----------
    def test_today_followup_of_open_deal_is_listed(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0)
        self.add_follow_up(c["id"], content="今天要报价", next_date=day(0), deal_id=deal["id"])

        board = self.dashboard()
        self.assertEqual(len(board["today_followups"]), 1)
        item = board["today_followups"][0]
        self.assertEqual(item["customer_id"], c["id"])
        self.assertEqual(item["customer_name"], "张伟")
        self.assertEqual(item["deal_id"], deal["id"])
        self.assertEqual(item["deal_stage"], "quote")
        self.assertEqual(item["content"], "今天要报价")
        self.assertEqual(item["next_date"], day(0))
        self.assertEqual(item["days_overdue"], 0)

    def test_overdue_sorted_oldest_first_and_future_excluded(self):
        """每个客户只看最近一条跟进；逾期按天数倒序，未来日期不进列表（PLANNER-V3 §6.1）"""
        a = self.create_customer(name="李娜")
        self.add_follow_up(a["id"], content="三天前该打", next_date=day(-3))
        b = self.create_customer(name="周强")
        self.add_follow_up(b["id"], content="昨天该打", next_date=day(-1))
        d = self.create_customer(name="孙丽")
        self.add_follow_up(d["id"], content="今天打", next_date=day(0))
        e = self.create_customer(name="吴敏")
        self.add_follow_up(e["id"], content="明天打", next_date=day(1))
        self.add_follow_up(e["id"], content="没定日期")

        items = self.dashboard()["today_followups"]
        self.assertEqual([i["content"] for i in items], ["三天前该打", "昨天该打", "今天打"])
        self.assertEqual([i["days_overdue"] for i in items], [3, 1, 0])

    def test_new_follow_up_replaces_old_one(self):
        """同一客户记了新跟进 → 旧的待跟进自动消失（定稿核心验收点）"""
        c = self.create_customer(name="李娜")
        self.add_follow_up(c["id"], content="旧记录", next_date=day(-2))
        self.assertEqual([i["content"] for i in self.dashboard()["today_followups"]], ["旧记录"])
        self.add_follow_up(c["id"], content="新记录", next_date=day(-10))
        self.assertEqual([i["content"] for i in self.dashboard()["today_followups"]], ["新记录"])

    def test_closed_deals_do_not_enter_today_followups(self):
        c = self.create_customer(name="王强")
        won_deal = self.create_deal(c["id"], amount=8000.0)
        lost_deal = self.create_deal(c["id"])
        self.add_follow_up(c["id"], content="won 后不该提醒", next_date=day(-1), deal_id=won_deal["id"])
        self.add_follow_up(c["id"], content="lost 后不该提醒", next_date=day(-1), deal_id=lost_deal["id"])
        self.add_follow_up(c["id"], content="只挂客户的跟进要提醒", next_date=day(-1))

        self._win_and_confirm_deal(won_deal["id"])
        self.client.post(f"/api/crm/deals/{lost_deal['id']}/lose", json={"lost_reason": "price"})

        items = self.dashboard()["today_followups"]
        self.assertEqual([i["content"] for i in items], ["只挂客户的跟进要提醒"])
        self.assertIsNone(items[0]["deal_id"])
        self.assertIsNone(items[0]["deal_stage"])

    def test_followup_after_won_excluded_even_if_recorded_before(self):
        """已成交的商机，旧待办也要消失（避免成交后还天天提醒）。"""
        c = self.create_customer(name="赵敏")
        deal = self.create_deal(c["id"], amount=5000.0)
        self.add_follow_up(c["id"], content="回访", next_date=day(-2), deal_id=deal["id"])
        self.assertEqual(len(self.dashboard()["today_followups"]), 1)

        self._win_and_confirm_deal(deal["id"])
        self.assertEqual(self.dashboard()["today_followups"], [])

    # ---------- 本月成交 ----------
    def test_month_won_counts_only_this_month(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0)
        self._win_and_confirm_deal(deal["id"])

        # 上月成交（直接落库，closed_at 是本地无时区格式）+ 本月还在 lead 的单
        from tests._util import insert_deal

        insert_deal(c["id"], stage="won", amount=9000.0, closed_at=f"{last_month_day()}T10:00:00")
        d_stage = self.create_deal(c["id"], amount=3000.0)
        self.client.put(f"/api/crm/deals/{d_stage['id']}", json={"stage": "confirm"})

        board = self.dashboard()
        self.assertEqual(board["month_won"]["count"], 1)
        self.assertEqual(board["month_won"]["amount"], 12000.0)
        self.assertEqual(board["stats"]["month_won"]["count"], 1)

    def test_month_won_zero_when_nothing_closed(self):
        c = self.create_customer(name="李娜")
        self.create_deal(c["id"], amount=5000.0)
        board = self.dashboard()
        self.assertEqual(board["month_won"], {"count": 0, "amount": 0.0})

    def test_month_won_sums_multiple_deals(self):
        c = self.create_customer(name="王强")
        for amount in (12000.0, 8000.0):
            deal = self.create_deal(c["id"], amount=amount)
            self._win_and_confirm_deal(deal["id"])
        board = self.dashboard()
        self.assertEqual(board["month_won"]["count"], 2)
        self.assertEqual(board["month_won"]["amount"], 20000.0)

    # ---------- 统计 ----------
    def test_stats_shape_and_values(self):
        c1 = self.create_customer(name="老客甲")
        self.create_deal(c1["id"], amount=100.0)
        self.create_deal(c1["id"], amount=200.0, stage="quote")
        c2 = self.create_customer(name="新客乙")
        deal = self.create_deal(c2["id"], amount=5000.0)
        self._win_and_confirm_deal(deal["id"])

        stats = self.dashboard()["stats"]
        self.assertEqual(stats["customers_total"], 2)
        self.assertEqual(set(stats["deals_by_stage"]), set(STAGES), "阶段键要全，缺的补 0")
        # 定稿：新建商机默认 quote，所以「老客甲两单」+「显式 quote 单」= 3 单里 2 单 quote
        self.assertEqual(stats["deals_by_stage"]["quote"], 2)
        self.assertEqual(stats["deals_by_stage"]["won"], 1)
        self.assertEqual(stats["deals_by_stage"]["confirm"], 0)
        self.assertEqual(stats["deals_by_stage"]["lost"], 0)
        self.assertEqual(stats["month_new_customers"], 2)
        self.assertEqual(stats["repeat_customers"], 1, "老客甲名下 2 单")
        self.assertEqual(stats["month_won"], {"count": 1, "amount": 5000.0})

    def test_dashboard_requires_auth(self):
        from tests._util import open_client

        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get("/api/crm/dashboard").status_code, 401)


if __name__ == "__main__":
    unittest.main()
