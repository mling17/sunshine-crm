"""商机标签：系统/自动标签与手动标签共用标签主表。"""

from __future__ import annotations

from app.errors import ApiError
from app.models import MAX_TAGS
from app.security import now_iso
from app.timeline import add_entry

AUTO_TAG_SOURCE = "auto"
MANUAL_TAG_SOURCE = "manual"


def ensure_deal_tags_editable(conn, deal_id: int) -> None:
    """商机生成订单后整体归档，已有标签只读。"""
    order = conn.execute(
        "SELECT id FROM orders WHERE deal_id = ? AND is_delete = 0 LIMIT 1",
        (deal_id,),
    ).fetchone()
    if order is not None:
        raise ApiError(
            409,
            "deal_tags_locked",
            "商机已生成订单并归档，标签不能再添加或删除",
        )


def list_deal_tags(conn, deal_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT dt.id, t.name, dt.source"
        " FROM deal_tags dt JOIN tags t ON t.id = dt.tag_id"
        " WHERE dt.deal_id = ? AND dt.is_delete = 0 AND t.is_delete = 0"
        " ORDER BY CASE dt.source WHEN 'auto' THEN 0 ELSE 1 END, dt.id",
        (deal_id,),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "source": row["source"],
            "deletable": row["source"] == MANUAL_TAG_SOURCE,
        }
        for row in rows
    ]


def _tag_id(conn, name: str) -> int:
    now = now_iso()
    conn.execute(
        "INSERT INTO tags (name, created_at) VALUES (?, ?)"
        " ON CONFLICT(name) DO UPDATE SET is_delete = 0, update_time = ?",
        (name, now, now),
    )
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def _link_tag(conn, deal_id: int, name: str, source: str) -> None:
    now = now_iso()
    tag_id = _tag_id(conn, name)
    conn.execute(
        "INSERT INTO deal_tags"
        " (deal_id, tag_id, source, created_at, updated_at, create_time, update_time, is_delete)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
        " ON CONFLICT(deal_id, tag_id, source) DO UPDATE SET"
        " is_delete = 0, updated_at = ?, update_time = ?",
        (deal_id, tag_id, source, now, now, now, now, now, now),
    )


def sync_pending_quote_tags(conn, deal_id: int) -> None:
    """按待客户确认报价单重建自动标签；重新报价后自动清掉。"""
    now = now_iso()
    conn.execute(
        "UPDATE deal_tags SET is_delete = 1, updated_at = ?, update_time = ?"
        " WHERE deal_id = ? AND source = ? AND is_delete = 0",
        (now, now, deal_id, AUTO_TAG_SOURCE),
    )
    pending = conn.execute(
        "SELECT id, amount FROM deal_quotes"
        " WHERE deal_id = ? AND status = 'pending' AND is_delete = 0"
        " ORDER BY id",
        (deal_id,),
    ).fetchall()
    if not pending:
        return
    _link_tag(conn, deal_id, "待确认", AUTO_TAG_SOURCE)
    for quote in pending:
        _link_tag(
            conn,
            deal_id,
            f"金额 ¥{float(quote['amount'] or 0):,.2f}",
            AUTO_TAG_SOURCE,
        )


def add_manual_tag(conn, deal_id: int, raw_name: str) -> list[dict]:
    name = (raw_name or "").strip()
    if not name:
        raise ApiError(400, "deal_tag_required", "标签名称不能为空")
    if len(name) > 32:
        raise ApiError(400, "deal_tag_too_long", "标签名称不能超过 32 个字")
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM deal_tags"
        " WHERE deal_id = ? AND source = ? AND is_delete = 0",
        (deal_id, MANUAL_TAG_SOURCE),
    ).fetchone()["n"]
    if int(count) >= MAX_TAGS:
        raise ApiError(400, "deal_tag_limit", f"商机最多添加 {MAX_TAGS} 个手动标签")
    _link_tag(conn, deal_id, name, MANUAL_TAG_SOURCE)
    add_entry(
        conn,
        object_type="deal",
        object_id=deal_id,
        kind="change",
        deal_id=deal_id,
        content=f"添加商机标签「{name}」",
        detail={"tags": {"from": None, "to": name}},
    )
    return list_deal_tags(conn, deal_id)


def delete_manual_tag(conn, deal_id: int, tag_link_id: int) -> list[dict]:
    row = conn.execute(
        "SELECT dt.id, dt.source, t.name FROM deal_tags dt"
        " JOIN tags t ON t.id = dt.tag_id"
        " WHERE dt.id = ? AND dt.deal_id = ? AND dt.is_delete = 0",
        (tag_link_id, deal_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "deal_tag_not_found", "商机标签不存在")
    if row["source"] != MANUAL_TAG_SOURCE:
        raise ApiError(409, "deal_tag_auto_locked", "自动生成的标签不能删除")
    now = now_iso()
    conn.execute(
        "UPDATE deal_tags SET is_delete = 1, updated_at = ?, update_time = ?"
        " WHERE id = ?",
        (now, now, tag_link_id),
    )
    add_entry(
        conn,
        object_type="deal",
        object_id=deal_id,
        kind="change",
        deal_id=deal_id,
        content=f"删除商机标签「{row['name']}」",
        detail={"tags": {"from": row["name"], "to": None}},
    )
    return list_deal_tags(conn, deal_id)


def backfill_pending_quote_tags(conn) -> None:
    for row in conn.execute(
        "SELECT DISTINCT deal_id FROM deal_quotes"
        " WHERE status = 'pending' AND is_delete = 0"
    ).fetchall():
        sync_pending_quote_tags(conn, int(row["deal_id"]))
