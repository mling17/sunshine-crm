"""线索标签：一次保存整组选择，并只记录一条变更履历。"""

from __future__ import annotations

from app.errors import ApiError
from app.models import MAX_TAGS
from app.security import now_iso
from app.timeline import add_entry


def _ensure_lead_editable(conn, lead_id: int) -> None:
    row = conn.execute(
        "SELECT status FROM leads WHERE id = ? AND is_delete = 0",
        (lead_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "lead_not_found", "线索不存在")
    if row["status"] in ("converted", "invalid"):
        raise ApiError(409, "lead_closed", "线索已转化或已无效，不能再修改标签")


def list_lead_tags(conn, lead_id: int) -> list[dict]:
    _ensure_lead_editable(conn, lead_id)
    rows = conn.execute(
        """
        SELECT t.id, t.name
        FROM lead_tags lt
        JOIN tags t ON t.id = lt.tag_id
        WHERE lt.lead_id = ? AND lt.is_delete = 0 AND t.is_delete = 0
        ORDER BY t.id
        """,
        (lead_id,),
    ).fetchall()
    return [{"id": int(row["id"]), "name": row["name"]} for row in rows]


def _tag_id(conn, name: str) -> int:
    now = now_iso()
    conn.execute(
        "INSERT INTO tags (name, created_at) VALUES (?, ?)"
        " ON CONFLICT(name) DO UPDATE SET is_delete = 0, update_time = ?",
        (name, now, now),
    )
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def replace_lead_tags(conn, lead_id: int, raw_names: list[str]) -> list[dict]:
    _ensure_lead_editable(conn, lead_id)
    current = list_lead_tags(conn, lead_id)
    names: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_names:
        name = (raw_name or "").strip()
        if not name:
            raise ApiError(400, "lead_tag_required", "标签名称不能为空")
        if len(name) > 32:
            raise ApiError(400, "lead_tag_too_long", "标签名称不能超过 32 个字")
        if name not in seen:
            names.append(name)
            seen.add(name)
    if len(names) > MAX_TAGS:
        raise ApiError(400, "lead_tag_limit", f"线索最多添加 {MAX_TAGS} 个标签")

    current_names = [tag["name"] for tag in current]
    if set(names) == set(current_names):
        return current

    now = now_iso()
    conn.execute(
        "UPDATE lead_tags SET is_delete = 1, update_time = ?"
        " WHERE lead_id = ? AND is_delete = 0",
        (now, lead_id),
    )
    for name in names:
        tag_id = _tag_id(conn, name)
        conn.execute(
            "INSERT INTO lead_tags (lead_id, tag_id) VALUES (?, ?)"
            " ON CONFLICT(lead_id, tag_id) DO UPDATE SET is_delete = 0, update_time = ?",
            (lead_id, tag_id, now),
        )
    conn.execute(
        "UPDATE leads SET updated_at = ?, update_time = ? WHERE id = ?",
        (now, now, lead_id),
    )

    added = [name for name in names if name not in current_names]
    removed = [name for name in current_names if name not in names]
    changes: list[str] = []
    if added:
        changes.append("添加「" + "、".join(added) + "」")
    if removed:
        changes.append("删除「" + "、".join(removed) + "」")
    add_entry(
        conn,
        object_type="lead",
        object_id=lead_id,
        kind="change",
        content="更新线索标签：" + "；".join(changes),
        detail={"tags": {"from": current_names, "to": names}},
    )
    return list_lead_tags(conn, lead_id)
