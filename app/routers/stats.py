"""统计页 8 块数据（PLANNER-V3 §5.9）。

口径（改动前先读这里）：
- 「本月」= 本地自然月（`date('now','localtime')`），禁 UTC；
- 漏斗按**累计到达**：won 计 3 段、confirm 计 2 段、quote 计 1 段，lost 不计；
- 线索转化率分母 = 线索池总数，不会 >100%；
- 老客/复购 = 该客户商机数 ≥ 2；
- 金额一律 ROUND(SUM(...), 2)，前端负责遮罩。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.db import db_conn
from app.enums import (
    AFTERSALE_TYPE_LABELS,
    DEAL_STAGE_LABELS,
    DEAL_STAGE_ORDER,
    ORDER_STATUS_LABELS,
    ORDER_STATUS_ORDER,
    SOURCE_LABELS,
)
from app.routers.auth import require_auth

router = APIRouter(
    prefix="/api/crm",
    tags=["stats"],
    dependencies=[Depends(require_auth)],
)


@router.get("/stats")
def get_stats(months: int = Query(default=6, ge=1, le=24)) -> dict:
    with db_conn() as conn:
        # ---------- KPI ----------
        customers_total = int(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0])
        month_new_customers = int(
            conn.execute(
                "SELECT COUNT(*) FROM customers"
                " WHERE datetime(created_at, 'localtime') >= datetime('now','localtime','start of month')"
            ).fetchone()[0]
        )
        row = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS a FROM deals"
            " WHERE stage='won' AND strftime('%Y-%m', closed_at) = strftime('%Y-%m','now','localtime')"
        ).fetchone()
        month_won = {"count": int(row["c"] or 0), "amount": round(float(row["a"] or 0), 2)}

        row = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS a FROM deals"
            " WHERE stage NOT IN ('won','lost')"
        ).fetchone()
        active_deals = int(row["c"] or 0)
        active_amount = round(float(row["a"] or 0), 2)

        repeat_customers = int(
            conn.execute(
                "SELECT COUNT(*) FROM (SELECT customer_id FROM deals GROUP BY customer_id"
                " HAVING COUNT(*) >= 2)"
            ).fetchone()[0]
        )
        pending_aftersales = int(
            conn.execute(
                "SELECT COUNT(*) FROM aftersales WHERE status IN ('pending','processing')"
            ).fetchone()[0]
        )

        # ---------- 近 N 月成交趋势 ----------
        month_rows = {
            str(r["k"]): float(r["a"] or 0)
            for r in conn.execute(
                "SELECT strftime('%Y-%m', closed_at) AS k, COALESCE(SUM(amount),0) AS a"
                " FROM deals WHERE stage='won' AND closed_at IS NOT NULL"
                " GROUP BY k"
            ).fetchall()
        }
        this_month = conn.execute(
            "SELECT strftime('%Y-%m','now','localtime')"
        ).fetchone()[0]
        trend = []
        for offset in range(months - 1, -1, -1):
            # 必须先归一化到月初再减月：10-31 减 1 个月会被 SQLite 进位成 10 月（经典坑）
            key = conn.execute(
                "SELECT strftime('%Y-%m','now','localtime','start of month', ?)",
                (f"-{offset} months",),
            ).fetchone()[0]
            trend.append(
                {
                    "label": f"{int(key.split('-')[1])}月",
                    "key": key,
                    "value": round(month_rows.get(key, 0.0), 2),
                    "highlight": key == this_month,
                }
            )

        # ---------- 漏斗：累计到达 ----------
        stage_counts = {
            row["stage"]: int(row["n"])
            for row in conn.execute("SELECT stage, COUNT(*) AS n FROM deals GROUP BY stage").fetchall()
        }
        reached = {
            "quote": stage_counts.get("quote", 0) + stage_counts.get("confirm", 0) + stage_counts.get("won", 0),
            "confirm": stage_counts.get("confirm", 0) + stage_counts.get("won", 0),
            "won": stage_counts.get("won", 0),
        }
        funnel = [
            {"key": key, "label": DEAL_STAGE_LABELS.get(key, key), "value": reached[key]}
            for key in ("quote", "confirm", "won")
        ]

        # ---------- 线索转化 ----------
        lead_rows = {
            row["status"]: int(row["n"])
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM leads"
                " WHERE is_delete = 0 GROUP BY status"
            ).fetchall()
        }
        lead_total = sum(lead_rows.values())
        converted = lead_rows.get("converted", 0)
        lead_conversion = {
            "total": lead_total,
            "following": lead_rows.get("following", 0) + lead_rows.get("new", 0),
            "converted": converted,
            "invalid": lead_rows.get("invalid", 0),
            "rate": round(converted / lead_total * 100, 1) if lead_total else 0.0,
        }

        # ---------- 分布 ----------
        deals_by_stage = [
            {
                "key": stage,
                "label": DEAL_STAGE_LABELS.get(stage, stage),
                "value": stage_counts.get(stage, 0),
                "cls": "ok" if stage == "won" else ("danger" if stage == "lost" else ""),
            }
            for stage in DEAL_STAGE_ORDER
        ]
        order_counts = {
            row["status"]: int(row["n"])
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status").fetchall()
        }
        orders_by_status = [
            {"key": status, "label": ORDER_STATUS_LABELS.get(status, status), "value": order_counts.get(status, 0)}
            for status in ORDER_STATUS_ORDER
        ]
        source_counts = {
            row["source"]: int(row["n"])
            for row in conn.execute("SELECT source, COUNT(*) AS n FROM customers GROUP BY source").fetchall()
        }
        customer_sources = sorted(
            [
                {"key": key or "unknown", "label": SOURCE_LABELS.get(key or "", key or "未填"), "value": value}
                for key, value in source_counts.items()
            ],
            key=lambda x: x["value"],
            reverse=True,
        )
        as_counts = {
            row["type"]: int(row["n"])
            for row in conn.execute("SELECT type, COUNT(*) AS n FROM aftersales GROUP BY type").fetchall()
        }
        aftersale_types = sorted(
            [
                {"key": key, "label": AFTERSALE_TYPE_LABELS.get(key, key), "value": value}
                for key, value in as_counts.items()
            ],
            key=lambda x: x["value"],
            reverse=True,
        )

    return {
        "kpis": {
            "customers_total": customers_total,
            "month_new_customers": month_new_customers,
            "month_won": month_won,
            "active_deals": active_deals,
            "active_deal_amount": active_amount,
            "repeat_customers": repeat_customers,
            "pending_aftersales": pending_aftersales,
        },
        "months": trend,
        "funnel": funnel,
        "lead_conversion": lead_conversion,
        "deals_by_stage": deals_by_stage,
        "orders_by_status": orders_by_status,
        "customer_sources": customer_sources,
        "aftersale_types": aftersale_types,
    }
