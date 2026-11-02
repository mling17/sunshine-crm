"""统计页数据（工作台/统计定稿 + 近 7 天口径）。

统一口径：
- ``range=7d`` 表示含今天在内的 7 个自然日；其余区间从自然月起算；
- 所有“新增/成交/售后”均按本地自然日筛选，禁止直接用 UTC 日期跨零点；
- 线索漏斗只统计所选区间新建的线索，逐层取上一层的子集，避免出现 >100%；
- 金额一律保留两位小数，前端负责金额遮罩。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.db import db_conn
from app.enums import (
    AFTERSALE_STATUS_LABELS,
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


PERIODS: dict[str, dict[str, Any]] = {
    "7d": {
        "label": "近7天",
        "trend_title": "近 7 日成交走势",
        "trend_caption": "含今天在内的 7 个自然日",
        "trend_mode": "day",
    },
    "month": {
        "label": "本月",
        "trend_title": "本月成交走势",
        "trend_caption": "按成交日期统计",
        "trend_mode": "month_day",
    },
    "3m": {
        "label": "近3月",
        "trend_title": "月度成交趋势",
        "trend_caption": "近 3 个自然月，按成交金额",
        "trend_mode": "month",
    },
    "6m": {
        "label": "近6月",
        "trend_title": "月度成交趋势",
        "trend_caption": "近 6 个自然月，按成交金额",
        "trend_mode": "month",
    },
    "year": {
        "label": "今年",
        "trend_title": "年度成交趋势",
        "trend_caption": "今年 1 月至今，按成交金额",
        "trend_mode": "month",
    },
}

ORDER_TONES = {
    "pending_confirmation": "amber",
    "pending_payment": "red",
    "deposit_paid": "blue",
    "producing": "violet",
    "balance_paid": "cyan",
    "ready_to_ship": "cyan",
    "shipped": "blue",
    "completed": "green",
}
AFTERSALE_TONES = {"pending": "red", "processing": "amber", "done": "green", "rejected": "grey"}


def _normalize_period(value: str | None) -> str:
    key = str(value or "6m").strip().lower()
    return key if key in PERIODS else "6m"


def _range_start(key: str) -> str:
    """从 SQLite 本地日期出发计算区间起点，避免宿主与数据库时区不一致。"""
    expressions = {
        "7d": "date('now','localtime','-6 days')",
        "month": "date('now','localtime','start of month')",
        "3m": "date('now','localtime','start of month','-2 months')",
        "6m": "date('now','localtime','start of month','-5 months')",
        "year": "date('now','localtime','start of year')",
    }
    with db_conn() as conn:
        return str(
            conn.execute("SELECT " + expressions.get(key, expressions["6m"])).fetchone()[0]
        )


def _between(start: str, end: str, column: str, *, utc: bool = True) -> tuple[str, tuple[str, str]]:
    expr = f"date(datetime({column}, 'localtime'))" if utc else f"date({column})"
    return f"{expr} BETWEEN ? AND ?", (start, end)


def _daily_series(start: str, end: str, won_deals: list[dict]) -> list[dict]:
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    buckets: list[dict] = []
    cursor = start_day
    while cursor <= end_day:
        key = cursor.isoformat()
        matched = [d for d in won_deals if str(d.get("closed_date") or "") == key]
        buckets.append(
            {
                "label": f"{cursor.month}/{cursor.day}",
                "key": key,
                "value": round(sum(float(d["amount"] or 0) for d in matched), 2),
                "count": len(matched),
                "highlight": cursor == end_day,
            }
        )
        cursor += timedelta(days=1)
    return buckets


def _monthly_series(
    start: str,
    end: str,
    won_deals: list[dict],
    count: int | None = None,
) -> list[dict]:
    cursor = date.fromisoformat(start).replace(day=1)
    end_day = date.fromisoformat(end)
    buckets: list[dict] = []
    while cursor <= end_day:
        key = cursor.strftime("%Y-%m")
        matched = [d for d in won_deals if str(d.get("closed_date") or "").startswith(key)]
        buckets.append(
            {
                "label": f"{cursor.month}月",
                "key": key,
                "value": round(sum(float(d["amount"] or 0) for d in matched), 2),
                "count": len(matched),
                "highlight": key == end_day.strftime("%Y-%m"),
            }
        )
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    if count:
        buckets = buckets[-count:]
    return buckets


def _source_name(item: dict) -> str:
    key = str(item.get("source") or "unknown")
    return SOURCE_LABELS.get(key, item.get("source_other") or "未填")


def _build_insights(
    sources: list[dict],
    products: list[dict],
    order_rows: dict[str, int],
    overdue_aftersales: int,
) -> list[dict]:
    insights: list[dict] = []
    source = next((s for s in sources if s["leads"] and s["rate"] > 0), None)
    if source:
        insights.append(
            {
                "icon": "源",
                "text": f"{source['name']}来源本期转化率 {source['rate']}%，为当前最高获客来源。",
            }
        )
    if products:
        product = products[0]
        insights.append(
            {
                "icon": "品",
                "text": f"{product['name']}成交额 {product['amount']:.2f} 元，暂列产品成交第一。",
            }
        )
    if overdue_aftersales:
        insights.append(
            {
                "icon": "售",
                "text": f"当前有 {overdue_aftersales} 单售后超过 3 天 SLA，建议优先闭环。",
            }
        )
    elif order_rows.get("pending_payment") or order_rows.get("balance_paid"):
        insights.append(
            {
                "icon": "单",
                "text": (
                    f"当前待支付 {order_rows.get('pending_payment', 0)} 单，"
                    f"待收尾款 {order_rows.get('balance_paid', 0)} 单。"
                ),
            }
        )
    return insights[:3]


@router.get("/stats")
def get_stats(
    months: int = Query(default=6, ge=1, le=24),
    range_key: str = Query(default="6m", alias="range"),
    period: str | None = Query(default=None),
) -> dict:
    """返回工作台统计页所需的 KPI、趋势、漏斗和分布数据。

    ``period`` 是 ``range`` 的兼容别名；来源/产品图表使用同一时间区间。
    """
    key = _normalize_period(period or range_key)
    start = _range_start(key)
    with db_conn() as conn:
        end = str(conn.execute("SELECT date('now','localtime')").fetchone()[0])

        lead_where, lead_args = _between(start, end, "created_at")
        deal_where, deal_args = _between(start, end, "created_at")
        order_where, order_args = _between(start, end, "created_at")
        aftersale_where, aftersale_args = _between(start, end, "created_at")

        leads = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT id, source, source_other, status, converted_deal_id,
                       converted_customer_id, created_at
                  FROM leads
                 WHERE is_delete = 0 AND {lead_where}
                 ORDER BY datetime(created_at) DESC, id DESC
                """,
                lead_args,
            ).fetchall()
        ]
        deals = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT id, customer_id, stage, amount, closed_at, order_id,
                       product_type, model, product_code_snapshot,
                       product_name_snapshot, created_at
                  FROM deals
                 WHERE is_delete = 0 AND {deal_where}
                """,
                deal_args,
            ).fetchall()
        ]
        all_deals = {
            int(row["id"]): dict(row)
            for row in conn.execute(
                """
                SELECT id, customer_id, stage, amount, closed_at, order_id,
                       product_type, model, product_code_snapshot,
                       product_name_snapshot, created_at
                  FROM deals WHERE is_delete = 0
                """
            ).fetchall()
        }
        orders = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT id, deal_id, status, amount, created_at
                  FROM orders
                 WHERE is_delete = 0 AND {order_where}
                """,
                order_args,
            ).fetchall()
        ]
        all_orders = [
            dict(row)
            for row in conn.execute(
                "SELECT id, deal_id, status, amount, created_at FROM orders WHERE is_delete = 0"
            ).fetchall()
        ]
        aftersales = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT id, type, status, description, created_at
                  FROM aftersales
                 WHERE is_delete = 0 AND {aftersale_where}
                """,
                aftersale_args,
            ).fetchall()
        ]

        customers_total = int(
            conn.execute("SELECT COUNT(*) FROM customers WHERE is_delete = 0").fetchone()[0]
        )
        month_new_customers = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM customers
                 WHERE is_delete = 0
                   AND datetime(created_at, 'localtime') >= datetime('now','localtime','start of month')
                """
            ).fetchone()[0]
        )
        repeat_customers = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT customer_id FROM deals
                     WHERE is_delete = 0
                     GROUP BY customer_id HAVING COUNT(*) >= 2
                )
                """
            ).fetchone()[0]
        )
        customer_source_counts = {
            str(row["source"] or ""): int(row["n"])
            for row in conn.execute(
                """
                SELECT source, COUNT(*) AS n FROM customers
                 WHERE is_delete = 0
                   AND date(datetime(created_at,'localtime')) BETWEEN ? AND ?
                 GROUP BY source
                """,
                (start, end),
            ).fetchall()
        }
        pending_aftersales = int(
            conn.execute(
                "SELECT COUNT(*) FROM aftersales"
                " WHERE is_delete = 0 AND status IN ('pending','processing')"
            ).fetchone()[0]
        )

        # 成交趋势：closed_at 是本地无时区业务时间，不再做 UTC 换算。
        won_where, won_args = _between(start, end, "closed_at", utc=False)
        won_deals = [
            {
                **dict(row),
                "closed_date": str(row["closed_at"] or "")[:10],
                "amount": float(row["amount"] or 0),
            }
            for row in conn.execute(
                f"""
                SELECT id, amount, closed_at FROM deals
                 WHERE is_delete = 0 AND stage = 'won'
                   AND closed_at IS NOT NULL AND {won_where}
                """,
                won_args,
            ).fetchall()
        ]

        current_month_won = [
            d for d in won_deals if str(d.get("closed_date") or "").startswith(end[:7])
        ]
        month_won = {
            "count": len(current_month_won),
            "amount": round(sum(d["amount"] for d in current_month_won), 2),
        }
        period_won = {
            "count": len(won_deals),
            "amount": round(sum(d["amount"] for d in won_deals), 2),
        }

        stage_counts = {stage: 0 for stage in DEAL_STAGE_ORDER}
        for row in deals:
            if row["stage"] in stage_counts:
                stage_counts[row["stage"]] += 1
        active_deals = sum(
            count for stage, count in stage_counts.items() if stage not in ("won", "lost")
        )
        active_amount = round(
            sum(float(d["amount"] or 0) for d in deals if d["stage"] not in ("won", "lost")),
            2,
        )

        lead_total = len(leads)
        converted_leads = [lead for lead in leads if lead["status"] == "converted"]
        converted = len(converted_leads)
        lead_conversion = {
            "total": lead_total,
            "following": sum(1 for lead in leads if lead["status"] in ("new", "following")),
            "converted": converted,
            "invalid": sum(1 for lead in leads if lead["status"] == "invalid"),
            "rate": round(converted / lead_total * 100, 1) if lead_total else 0.0,
        }

        orders_by_deal: dict[int, list[dict]] = {}
        for order in all_orders:
            orders_by_deal.setdefault(int(order["deal_id"]), []).append(order)

        funnel_confirmed = 0
        funnel_ordered = 0
        funnel_completed = 0
        for lead in converted_leads:
            deal_id = int(lead["converted_deal_id"] or 0)
            deal = all_deals.get(deal_id)
            if not deal:
                continue
            if deal["stage"] in ("confirm", "won") or deal.get("order_id"):
                funnel_confirmed += 1
            linked_orders = orders_by_deal.get(deal_id, [])
            if deal.get("order_id") or linked_orders:
                funnel_ordered += 1
            if any(order["status"] == "completed" for order in linked_orders):
                funnel_completed += 1

        lead_funnel = [
            {"key": "lead", "label": "新增线索", "value": lead_total},
            {"key": "converted", "label": "已转化", "value": converted},
            {"key": "confirm", "label": "客户已确认", "value": funnel_confirmed},
            {"key": "ordered", "label": "已生成订单", "value": funnel_ordered},
            {"key": "completed", "label": "已完成订单", "value": funnel_completed},
        ]
        sales_funnel = [
            {
                "key": stage,
                "label": DEAL_STAGE_LABELS.get(stage, stage),
                "value": (
                    stage_counts.get("quote", 0)
                    + stage_counts.get("confirm", 0)
                    + stage_counts.get("won", 0)
                    if stage == "quote"
                    else stage_counts.get("confirm", 0) + stage_counts.get("won", 0)
                    if stage == "confirm"
                    else stage_counts.get("won", 0)
                ),
            }
            for stage in ("quote", "confirm", "won")
        ]

        deals_by_stage = [
            {
                "key": stage,
                "label": DEAL_STAGE_LABELS.get(stage, stage),
                "value": stage_counts[stage],
                "tone": "green" if stage == "won" else "red" if stage == "lost" else
                "amber" if stage == "confirm" else "blue",
            }
            for stage in DEAL_STAGE_ORDER
        ]

        order_counts = {status: 0 for status in ORDER_STATUS_ORDER}
        for order in orders:
            if order["status"] in order_counts:
                order_counts[order["status"]] += 1
        orders_by_status = [
            {
                "key": status,
                "label": ORDER_STATUS_LABELS.get(status, status),
                "value": order_counts[status],
            }
            for status in ORDER_STATUS_ORDER
        ]
        order_status = [
            {
                "key": status,
                "label": ORDER_STATUS_LABELS.get(status, status),
                "value": order_counts[status],
                "tone": ORDER_TONES.get(status, "grey"),
            }
            for status in ORDER_STATUS_ORDER
        ]

        source_map: dict[str, dict] = {}
        for lead in leads:
            name = _source_name(lead)
            item = source_map.setdefault(
                name,
                {"name": name, "leads": 0, "converted": 0, "won": 0, "amount": 0.0},
            )
            item["leads"] += 1
            if lead["status"] == "converted":
                item["converted"] += 1
            deal = all_deals.get(int(lead["converted_deal_id"] or 0))
            if deal and str(deal.get("closed_at") or "")[:10] >= start:
                if deal["stage"] == "won":
                    item["won"] += 1
                    item["amount"] += float(deal["amount"] or 0)
        sources = []
        for item in sorted(source_map.values(), key=lambda x: (-x["leads"], x["name"])):
            item["rate"] = round(item["converted"] / item["leads"] * 100, 1) if item["leads"] else 0.0
            item["amount"] = round(item["amount"], 2)
            sources.append(item)

        customer_sources = sorted(
            [
                {
                    "key": source or "unknown",
                    "label": SOURCE_LABELS.get(source or "", "未填"),
                    "value": value,
                }
                for source, value in customer_source_counts.items()
            ],
            key=lambda item: item["value"],
            reverse=True,
        )

        service_counts = {status: 0 for status in AFTERSALE_STATUS_LABELS}
        service_type_counts: dict[str, int] = {}
        for row in aftersales:
            service_counts[row["status"]] = service_counts.get(row["status"], 0) + 1
            service_type_counts[row["type"]] = service_type_counts.get(row["type"], 0) + 1
        service_status = [
            {
                "key": status,
                "label": label,
                "value": service_counts.get(status, 0),
                "tone": AFTERSALE_TONES.get(status, "grey"),
            }
            for status, label in AFTERSALE_STATUS_LABELS.items()
            if status != "rejected"
        ]
        aftersale_types = sorted(
            [
                {
                    "key": status,
                    "label": AFTERSALE_TYPE_LABELS.get(status, status),
                    "value": value,
                    "tone": ("blue", "amber", "red", "cyan", "grey")[index % 5],
                }
                for index, (status, value) in enumerate(service_type_counts.items())
            ],
            key=lambda item: item["value"],
            reverse=True,
        )

        overdue_where, overdue_args = _between(start, end, "a.created_at")
        overdue_aftersales = int(
            conn.execute(
                f"""
                SELECT COUNT(*) FROM aftersales a
                 WHERE a.is_delete = 0
                   AND a.status IN ('pending','processing')
                   AND {overdue_where}
                   AND julianday(date('now','localtime')) - julianday(date(a.created_at)) > 3
                """,
                overdue_args,
            ).fetchone()[0]
        )

        # 产品成交排行：多产品报价单按明细汇总；旧单没有明细时回退到商机快照。
        product_rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT COALESCE(NULLIF(di.product_name_snapshot,''), NULLIF(d.product_name_snapshot,''),
                                NULLIF(d.product_type,''), '未命名产品') AS name,
                       COALESCE(NULLIF(di.product_code_snapshot,''), NULLIF(d.product_code_snapshot,''),
                                '—') AS code,
                       COALESCE(SUM(di.quantity), 0) AS count,
                       COALESCE(SUM(di.amount), 0) AS amount
                  FROM deal_items di
                  JOIN deals d ON d.id = di.deal_id
                 WHERE d.is_delete = 0 AND di.is_delete = 0
                   AND d.stage = 'won' AND d.closed_at IS NOT NULL AND {won_where}
                 GROUP BY name, code
                 ORDER BY amount DESC, count DESC
                 LIMIT 7
                """,
                won_args,
            ).fetchall()
        ]
        if not product_rows:
            product_rows = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT COALESCE(NULLIF(product_name_snapshot,''),
                                    NULLIF(product_type,''), '未命名产品') AS name,
                           COALESCE(NULLIF(product_code_snapshot,''), '—') AS code,
                           COUNT(*) AS count,
                           COALESCE(SUM(amount), 0) AS amount
                      FROM deals
                     WHERE is_delete = 0 AND stage = 'won'
                       AND closed_at IS NOT NULL AND {won_where}
                     GROUP BY name, code
                     ORDER BY amount DESC, count DESC
                     LIMIT 7
                    """,
                    won_args,
                ).fetchall()
            ]
        products = [
            {
                "name": row["name"],
                "code": row["code"],
                "count": int(row["count"] or 0),
                "amount": round(float(row["amount"] or 0), 2),
            }
            for row in product_rows
        ]

        meta = PERIODS[key]
        if meta["trend_mode"] in ("day", "month_day"):
            trend_rows = _daily_series(start, end, won_deals)
        else:
            trend_rows = _monthly_series(start, end, won_deals)

        summary = {
            "newLeads": lead_total,
            "leadRate": lead_conversion["rate"],
            "convertedLeads": converted,
            "wonAmount": period_won["amount"],
            "wonCount": period_won["count"],
            "avgDeal": round(period_won["amount"] / period_won["count"], 2) if period_won["count"] else 0.0,
            "aftersales": len(aftersales),
            "overdueAftersales": overdue_aftersales,
        }

        return {
            "range": {
                "key": key,
                "label": meta["label"],
                "start": start,
                "end": end,
            },
            "kpis": {
                "customers_total": customers_total,
                "month_new_customers": month_new_customers,
                "month_won": month_won,
                "active_deals": active_deals,
                "active_deal_amount": active_amount,
                "repeat_customers": repeat_customers,
                "pending_aftersales": pending_aftersales,
            },
            "summary": summary,
            "months": trend_rows,
            "trend": {
                "title": meta["trend_title"],
                "caption": meta["trend_caption"],
                "labels": [item["label"] for item in trend_rows],
                "values": [item["value"] for item in trend_rows],
                "counts": [item["count"] for item in trend_rows],
            },
            "funnel": sales_funnel,
            "lead_funnel": lead_funnel,
            "lead_conversion": lead_conversion,
            "deals_by_stage": deals_by_stage,
            "orders_by_status": orders_by_status,
            "order_status": order_status,
            "customer_sources": customer_sources,
            "sources": sources,
            "products": products,
            "service_status": service_status,
            "aftersale_types": aftersale_types,
            "insights": _build_insights(sources, products, order_counts, overdue_aftersales),
        }
