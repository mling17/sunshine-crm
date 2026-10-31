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

from app.enums import TIMELINE_TYPE_LABELS, DRIVE_TYPE_LABELS

#: kind 的中文（前端也可直接用出参 type_label，避免自己维护映射）
KIND_LABELS = TIMELINE_TYPE_LABELS


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
        # 订单「创建」事件在商机侧已由 follow_ups(kind='order') 记过一条，避免重复展示
        items.extend(
            e
            for e in order_events(conn, object_type=object_type, object_id=object_id)
            if e["type"] != "order"
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


def change_summary(old: dict, new: dict, columns: Iterable[str]) -> tuple[list[str], dict]:
    """对比字段变化，返回（中文摘要列表, detail 字典）。没有变化返回空。"""
    labels = {
        "product_type": "产品类型",
        "model": "型号",
        "spec": "尺寸",
        "amount": "金额",
        "drive_type": "手动/电动",
        "note": "备注",
    }
    lines: list[str] = []
    detail: dict[str, dict] = {}
    for column in columns:
        if column not in new:
            continue
        before, after = old.get(column), new[column]
        if before == after:
            continue
        name = labels.get(column, column)
        if column == "drive_type":
            before = DRIVE_TYPE_LABELS.get(str(before), before) if before is not None else before
            after = DRIVE_TYPE_LABELS.get(str(after), after) if after is not None else after
        if column == "amount":
            lines.append(f"{name}由 ¥{before} 改为 ¥{after}")
        else:
            lines.append(f"{name}由 {before} 改为 {after}")
        detail[column] = {"from": old.get(column), "to": new[column]}
    return lines, detail