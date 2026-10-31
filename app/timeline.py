"""对象履历（timeline）读写 —— 商机 / 客户 / 订单 / 售后共用。

PLANNER-V3 §3.5：`follow_ups` 扩成「对象履历」表：
    kind='follow'  → 真实跟进行（用户记的，带 method / next_date / 附件）
    kind=其它      → 系统自动写入（create/change/stage/order/aftersale/pay/ship/address）

约定：
- 一律走 ``add_entry`` 写、``entries_for`` 读，router 不许自己拼 INSERT；
- 中文只出现在 content/type_label，落库的 kind 是英文；
- 附件挂在 kind='follow' 的履历上（`attachments.object_type='follow_up'`）。
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from app import labels as label_svc
from app.enums import TIMELINE_TYPE_LABELS

#: kind 的中文（前端也可直接用出参 type_label，避免自己维护映射）
KIND_LABELS = TIMELINE_TYPE_LABELS

#: 编辑履历统一使用的中文字段名。未列出的字段仍会显示原名，避免静默漏记。
FIELD_LABELS = {
    "name": "姓名",
    "phone": "电话",
    "wechat": "微信",
    "lead_type": "类型",
    "customer_type": "客户类型",
    "company_name": "公司名",
    "source": "来源",
    "source_other": "来源补充",
    "location": "地区",
    "note": "备注",
    "intent_level": "意向",
    "owner": "负责人",
    "tags": "标签",
    "product_id": "关联产品",
    "product_code_snapshot": "产品编码",
    "product_name_snapshot": "产品名称",
    "product_config_snapshot": "产品配置",
    "product_type": "产品类型",
    "model": "型号",
    "spec": "尺寸",
    "amount": "金额",
    "deposit": "定金",
    "balance": "尾款",
    "drive_type": "手动/电动",
}

#: 枚举字段在履历中显示中文，detail 仍保存原始值供程序使用。
_VALUE_LABELERS = {
    "lead_type": label_svc.customer_type,
    "customer_type": label_svc.customer_type,
    "source": label_svc.source,
    "intent_level": label_svc.intent_level,
    "drive_type": label_svc.drive_type,
}
_MONEY_FIELDS = {"amount", "deposit", "balance"}


def add_entry(
    conn: sqlite3.Connection,
    *,
    object_type: str,
    object_id: int,
    kind: str,
    content: str,
    customer_id: int | None = None,
    deal_id: int | None = None,
    method: str | None = None,
    detail: dict | None = None,
    created_at: str | None = None,
    next_date: str | None = None,
) -> int:
    """写一条履历，返回 follow_ups.id。"""
    if customer_id is None and object_type == "deal":
        row = conn.execute(
            "SELECT customer_id FROM deals WHERE id = ?", (object_id,)
        ).fetchone()
        customer_id = row["customer_id"] if row else None
    if created_at is None:
        from app.security import now_iso

        created_at = now_iso()
    cur = conn.execute(
        "INSERT INTO follow_ups"
        " (object_type, object_id, customer_id, deal_id, method, kind, content, detail,"
        "  next_date, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            object_type,
            object_id,
            customer_id,
            deal_id,
            method,
            kind,
            content,
            json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
            next_date,
            created_at,
        ),
    )
    return int(cur.lastrowid or 0)


def _loads(raw: Any) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _files_for(conn: sqlite3.Connection, follow_up_ids: Iterable[int]) -> dict[int, list[dict]]:
    ids = [int(i) for i in follow_up_ids]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, object_id, file_name, mime_type, size FROM attachments"
        f" WHERE object_type = 'follow_up' AND object_id IN ({marks}) ORDER BY id",
        ids,
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for row in rows:
        out.setdefault(int(row["object_id"]), []).append(
            {
                "id": row["id"],
                "name": row["file_name"],
                "mime": row["mime_type"],
                "size": row["size"],
                "is_image": str(row["mime_type"] or "").startswith("image/"),
                "url": f"/api/crm/attachments/{row['id']}",
            }
        )
    return out


def entries_for(
    conn: sqlite3.Connection,
    *,
    object_type: str,
    object_id: int,
    include_order_events: bool = False,
    limit: int = 200,
) -> list[dict]:
    """读某个对象的履历（倒序）。

    ``include_order_events=True`` 时把订单事件流（order_status_log）也并进来 ——
    商机详情/订单详情都要求「订单每次操作都留痕」。
    """
    rows = conn.execute(
        "SELECT * FROM follow_ups"
        " WHERE (object_type = ? AND object_id = ?)"
        " ORDER BY datetime(created_at) DESC, id DESC LIMIT ?",
        (object_type, object_id, limit),
    ).fetchall()
    files = _files_for(conn, [row["id"] for row in rows if row["kind"] == "follow"])

    items: list[dict] = []
    for row in rows:
        kind = row["kind"] or "follow"
        items.append(
            {
                "at": row["created_at"],
                "type": kind,
                "type_label": KIND_LABELS.get(kind, kind),
                "content": row["content"],
                "method": row["method"],
                "next_date": row["next_date"],
                "detail": _loads(row["detail"]),
                "files": files.get(int(row["id"]), []),
                "follow_up_id": row["id"],
            }
        )

    if include_order_events:
        items.extend(
            e
            for e in order_events(conn, object_type=object_type, object_id=object_id)
            # 商机侧「生成订单」已由 follow_ups(kind='order') 记过，避免重复；订单侧要保留
            if not (object_type == "deal" and e["type"] == "order")
        )
        items.sort(key=lambda x: str(x.get("at") or ""), reverse=True)

    return items


def order_events(
    conn: sqlite3.Connection, *, object_type: str, object_id: int
) -> list[dict]:
    """订单事件流：商机对象取它的订单，订单对象直接取自己。"""
    if object_type == "order":
        order_row = conn.execute("SELECT id FROM orders WHERE id = ?", (object_id,)).fetchone()
    elif object_type == "deal":
        order_row = conn.execute(
            "SELECT id FROM orders WHERE deal_id = ?", (object_id,)
        ).fetchone()
    else:
        return []
    if order_row is None:
        return []

    rows = conn.execute(
        "SELECT * FROM order_status_log WHERE order_id = ?"
        " ORDER BY datetime(created_at) DESC, id DESC",
        (int(order_row["id"]),),
    ).fetchall()
    out = []
    for row in rows:
        kind = row["event_type"] or "stage"
        detail = _loads(row["detail"]) or {}
        out.append(
            {
                "at": row["created_at"],
                "type": kind,
                "type_label": KIND_LABELS.get(kind, kind),
                "content": row["note"] or "",
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "detail": detail,
                "files": [],
                "follow_up_id": None,
            }
        )
    return out


def _change_value(column: str, value: Any) -> str:
    """把字段值转成履历里可读的文案；空值也明确显示为“未填写”。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "未填写"
    labeler = _VALUE_LABELERS.get(column)
    if labeler is not None:
        return str(labeler(str(value)))
    if column in _MONEY_FIELDS:
        try:
            return f"¥{float(value):,.2f}"
        except (TypeError, ValueError):
            pass
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(items) if items else "未填写"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def change_summary(old: dict, new: dict, columns: Iterable[str]) -> tuple[list[str], dict]:
    """对比字段变化，返回（中文摘要列表, detail 字典）。

    每个摘要都包含“字段名 + 原值 + 新值”；detail 同时保留原始值与展示文案，
    便于页面直接展示和审计系统按字段读取。
    """
    lines: list[str] = []
    detail: dict[str, dict] = {}
    for column in columns:
        if column not in new:
            continue
        before, after = old.get(column), new[column]
        if before == after:
            continue
        name = FIELD_LABELS.get(column, column)
        before_text = _change_value(column, before)
        after_text = _change_value(column, after)
        lines.append(f"{name}由「{before_text}」改为「{after_text}」")
        detail[column] = {
            "label": name,
            "from": before,
            "to": after,
            "from_label": before_text,
            "to_label": after_text,
        }
    return lines, detail

def load_overdue_days(next_date: str | None) -> int:
    """next_date 距今天几天（>0 逾期，0 今天，负数/空 = 0）。统一口径，别各写一份。"""
    if not next_date:
        return 0
    from datetime import date, datetime as _dt

    try:
        due = _dt.strptime(str(next_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return 0
    return max((date.today() - due).days, 0)
