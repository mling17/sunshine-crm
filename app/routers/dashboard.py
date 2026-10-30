"""首页看板：今日待跟进 + 本月成交 + 简单统计。

口径（已拍板，别改成 UTC）：
- 「今天」= ``date('now','localtime')``，服务器在 CST；用 UTC 会跨零点错一天；
- 待跟进 = ``follow_ups.next_date`` 非空且 ``≤ 今天``，**且关联商机未闭环**
  （``won``/``lost`` 不再提醒；只挂客户的跟进照常提醒）；
- 本月成交 = ``deals.stage='won'`` 且 ``strftime('%Y-%m', closed_at)`` 等于本月
  （``closed_at`` 由 ``now_local_iso()`` 写成本地无时区格式，与这里同口径）；
- 本月新客 = ``customers.created_at`` 是 UTC ISO（带 Z），所以先用
  ``datetime(created_at,'localtime')`` 转本地再和「本月 1 号」比，避免月初 8 小时误差。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import db_conn
from app.models import (
    STAGES,
    STAGE_LABELS,
    DashboardOut,
    DashboardStatsOut,
    MonthWonOut,
    TodayFollowUpOut,
)
from app.routers.auth import require_auth

router = APIRouter(
    prefix="/api/crm",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)],
)

#: 待跟进：next_date ≤ 今天且商机未闭环；按「该打却没打」的天数倒序（最久的排最前）
_TODAY_FOLLOWUPS_SQL = """
SELECT fu.id, fu.customer_id, fu.deal_id, fu.content, fu.next_date,
       c.name AS customer_name,
       d.stage AS deal_stage,
       CAST(julianday(date('now','localtime')) - julianday(date(fu.next_date)) AS INTEGER) AS days_overdue
FROM follow_ups fu
JOIN customers c ON c.id = fu.customer_id
LEFT JOIN deals d ON d.id = fu.deal_id
WHERE fu.next_date IS NOT NULL
  AND TRIM(fu.next_date) <> ''
  AND date(fu.next_date) <= date('now','localtime')
  AND (d.id IS NULL OR d.stage NOT IN ('won', 'lost'))
ORDER BY date(fu.next_date) ASC, fu.id ASC
"""

#: 本月成交（金额按 deal.amount 汇总；deposit/balance 不参与，等 O2 确认）
_MONTH_WON_SQL = """
SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
FROM deals
WHERE stage = 'won'
  AND strftime('%Y-%m', closed_at) = strftime('%Y-%m', 'now', 'localtime')
"""

#: 订单状态统计（按 7 个状态分类）
_ORDERS_BY_STATUS_SQL = """
SELECT status, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
FROM orders
GROUP BY status
"""

#: 最近订单（按创建时间倒序）
_RECENT_ORDERS_SQL = """
SELECT o.id, o.order_no, c.name AS customer_name, o.amount, o.status, o.created_at
FROM orders o
JOIN customers c ON c.id = o.customer_id
ORDER BY o.created_at DESC
LIMIT 10
"""

#: 待处理售后单超期（超过3天）
_AFTERSALE_SLA_ALERTS_SQL = """
SELECT a.id, a.no, 
       CAST(julianday(date('now','localtime')) - julianday(date(a.created_at)) AS INTEGER) AS days_pending,
       o.order_no, c.name AS customer_name
FROM aftersales a
JOIN orders o ON o.id = a.order_id
JOIN customers c ON c.id = a.customer_id
WHERE a.status = 'pending'
  AND julianday(date('now','localtime')) - julianday(date(a.created_at)) > 3
ORDER BY a.created_at ASC
"""


def _month_won(conn) -> MonthWonOut:
    row = conn.execute(_MONTH_WON_SQL).fetchone()
    return MonthWonOut(count=int(row["count"] or 0), amount=float(row["amount"] or 0.0))


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard() -> DashboardOut:
    with db_conn() as conn:
        follow_rows = conn.execute(_TODAY_FOLLOWUPS_SQL).fetchall()
        month_won = _month_won(conn)

        customers_total = conn.execute(
            "SELECT COUNT(*) AS n FROM customers"
        ).fetchone()["n"]

        # 阶段计数：所有阶段都给键（含 0），前端不用做兜底
        deals_by_stage = {stage: 0 for stage in STAGES}
        for row in conn.execute(
            "SELECT stage, COUNT(*) AS n FROM deals GROUP BY stage"
        ).fetchall():
            deals_by_stage[row["stage"]] = row["n"]

        month_new_customers = conn.execute(
            """
            SELECT COUNT(*) AS n FROM customers
            WHERE datetime(created_at, 'localtime')
                  >= datetime('now', 'localtime', 'start of month')
            """
        ).fetchone()["n"]

        repeat_customers = conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
                SELECT customer_id FROM deals GROUP BY customer_id HAVING COUNT(*) >= 2
            )
            """
        ).fetchone()["n"]

        # 订单状态统计（7个状态）
        orders_by_status = {
            "pending_payment": {"count": 0, "amount": 0.0},
            "deposit_paid": {"count": 0, "amount": 0.0},
            "producing": {"count": 0, "amount": 0.0},
            "balance_paid": {"count": 0, "amount": 0.0},
            "ready_to_ship": {"count": 0, "amount": 0.0},
            "shipped": {"count": 0, "amount": 0.0},
            "completed": {"count": 0, "amount": 0.0},
        }
        for row in conn.execute(_ORDERS_BY_STATUS_SQL).fetchall():
            status = row["status"]
            if status in orders_by_status:
                orders_by_status[status]["count"] = int(row["count"] or 0)
                orders_by_status[status]["amount"] = float(row["amount"] or 0.0)

        # 最近订单
        recent_orders = []
        for row in conn.execute(_RECENT_ORDERS_SQL).fetchall():
            recent_orders.append({
                "id": row["id"],
                "order_no": row["order_no"],
                "customer_name": row["customer_name"],
                "amount": float(row["amount"] or 0.0),
                "status": row["status"],
                "status_label": None,  # 由前端填充
                "created_at": row["created_at"]
            })

        # 待处理售后单超期
        aftersale_sla_alerts = []
        for row in conn.execute(_AFTERSALE_SLA_ALERTS_SQL).fetchall():
            aftersale_sla_alerts.append({
                "id": row["id"],
                "no": row["no"],
                "days_pending": int(row["days_pending"] or 0),
                "order_no": row["order_no"],
                "customer_name": row["customer_name"]
            })

    today_followups = [
        TodayFollowUpOut(
            id=row["id"],
            customer_id=row["customer_id"],
            customer_name=row["customer_name"],
            deal_id=row["deal_id"],
            deal_stage=row["deal_stage"],
            deal_stage_label=STAGE_LABELS.get(row["deal_stage"]),
            content=row["content"],
            next_date=row["next_date"],
            days_overdue=int(row["days_overdue"] or 0),
        )
        for row in follow_rows
    ]

    return DashboardOut(
        today_followups=today_followups,
        month_won=month_won,
        stats=DashboardStatsOut(
            customers_total=int(customers_total),
            deals_by_stage=deals_by_stage,
            month_new_customers=int(month_new_customers),
            repeat_customers=int(repeat_customers),
            month_won=month_won,
            orders_by_status=orders_by_status,
            recent_orders=recent_orders,
            aftersale_sla_alerts=aftersale_sla_alerts,
        ),
    )
