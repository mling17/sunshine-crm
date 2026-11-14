"""线索创建与读取共享服务。"""

from __future__ import annotations

from collections.abc import Iterable

from app import labels
from app.errors import ApiError
from app.models import LeadOut, MAX_TAGS
from app.phone import canonicalize_mainland_mobile
from app.security import now_iso
from app.timeline import add_entry


def _legacy_phone(raw: object) -> str:
    return "".join(str(raw or "").split()).replace("-", "").replace("(", "").replace(")", "")


def _comparison_phone(raw: object) -> str:
    try:
        return canonicalize_mainland_mobile(raw)
    except ValueError:
        return _legacy_phone(raw)


def find_active_contact_by_phone(conn, phone: str) -> dict | None:
    """按规范化手机号查有效线索/客户，返回最小重复摘要。"""
    phone_key = _comparison_phone(phone)
    rows = conn.execute(
        "SELECT 'lead' AS object_type, id, name, phone, status"
        " FROM leads WHERE is_delete = 0"
        " UNION ALL "
        "SELECT 'customer' AS object_type, id, name, phone, 'converted' AS status"
        " FROM customers WHERE is_delete = 0"
    ).fetchall()
    for row in rows:
        if phone_key and phone_key == _comparison_phone(row["phone"]):
            return {
                "object_type": row["object_type"],
                "object_id": int(row["id"]),
                "name": row["name"] or "未知",
                "phone": phone_key,
                "status": row["status"],
            }
    return None


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result[:MAX_TAGS]


def _save_tags(conn, lead_id: int, tags: Iterable[str], now: str) -> None:
    for name in _normalize_tags(tags):
        conn.execute(
            "INSERT INTO tags (name, created_at) VALUES (?, ?)"
            " ON CONFLICT(name) DO UPDATE SET is_delete = 0, update_time = ?",
            (name, now, now),
        )
        tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        conn.execute(
            "INSERT INTO lead_tags (lead_id, tag_id) VALUES (?, ?)"
            " ON CONFLICT(lead_id, tag_id) DO UPDATE SET"
            " is_delete = 0, update_time = ?",
            (lead_id, tag_row["id"], now),
        )


def create_lead_record(
    conn,
    *,
    name: str | None,
    phone: str,
    wechat: str | None,
    lead_type: str,
    company_name: str | None,
    source: str,
    source_other: str | None,
    location: str | None,
    note: str | None,
    intent_level: str | None,
    owner: str | None,
    tags: Iterable[str],
    created_by: int,
    status: str = "new",
) -> int:
    duplicate = find_active_contact_by_phone(conn, phone)
    if duplicate:
        raise ApiError(
            status_code=409,
            code="duplicate_contact",
            message=f"联系方式已存在：{duplicate['name']}（{duplicate['phone']}）",
            duplicate_hint=duplicate,
        )

    now = now_iso()
    cur = conn.execute(
        """
        INSERT INTO leads
            (name, phone, wechat, lead_type, company_name, source, source_other,
             location, note, intent_level, status, owner, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            phone,
            wechat,
            lead_type,
            company_name,
            source,
            source_other,
            location,
            note,
            intent_level,
            status,
            owner,
            created_by,
            now,
            now,
        ),
    )
    lead_id = int(cur.lastrowid or 0)
    _save_tags(conn, lead_id, tags, now)
    add_entry(
        conn,
        object_type="lead",
        object_id=lead_id,
        kind="create",
        content="创建线索：" + (name or phone or wechat or ""),
    )
    return lead_id


def fetch_lead(conn, lead_id: int) -> LeadOut:
    row = conn.execute(
        """
        SELECT id, name, phone, wechat, lead_type, company_name, source,
               source_other, location, note, intent_level, status,
               invalid_reason, invalid_reason_other, converted_customer_id,
               converted_deal_id, owner, created_by, created_at, updated_at
        FROM leads WHERE id = ? AND is_delete = 0
        """,
        (lead_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "lead_not_found", "线索不存在")
    tag_rows = conn.execute(
        "SELECT t.name FROM tags t JOIN lead_tags lt ON t.id = lt.tag_id"
        " WHERE lt.lead_id = ? AND lt.is_delete = 0 AND t.is_delete = 0"
        " ORDER BY t.id",
        (lead_id,),
    ).fetchall()
    data = dict(row)
    data["intent_level_label"] = labels.intent_level(data.get("intent_level"))
    return LeadOut(**data, tags=[row[0] for row in tag_rows])


def user_id_for_username(conn, username: str) -> int:
    row = conn.execute(
        "SELECT id FROM users WHERE username = ? AND is_delete = 0",
        (username,),
    ).fetchone()
    if row is None:
        raise ApiError(401, "unauthorized", "认证失败")
    return int(row["id"])
