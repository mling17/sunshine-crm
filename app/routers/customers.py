"""客户档案：CRUD + 搜索分页 + 标签（多对多）+ 详情 + 级联删除。

- 全部接口要求登录（router 级 ``dependencies=[Depends(require_auth)]``）；
- 删除客户靠 DDL 的 ``ON DELETE CASCADE`` 级联清 deals/follow_ups/customer_tags，
  前提是连接上开了 ``PRAGMA foreign_keys=ON``（``app.db.connect`` 已处理）；
- 列表里的 ``deals_total`` / ``total_closed_amount`` 用相关子查询算，避免 N+1；
- 标签：``tags(name UNIQUE)`` 做字典，``customer_tags`` 做关联。写客户时按名字
  upsert 字典（同名永远复用同一个 tag_id），再整体替换该客户的关联行。
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import db_conn
from app.models import (
    MAX_TAGS,
    CustomerDetailOut,
    CustomerIn,
    CustomerListOut,
    CustomerOut,
    CustomerUpdate,
    DealOut,
    FollowUpOut,
)
from app.routers.auth import require_auth
from app.security import now_iso

router = APIRouter(
    prefix="/api/crm",
    tags=["customers"],
    dependencies=[Depends(require_auth)],
)

#: 客户出参的固定列（含两个复购口径子查询）；拼 JOIN / WHERE 时直接接在后面
_CUSTOMER_SELECT = """
SELECT c.id, c.name, c.phone, c.wechat, c.location, c.house_note,
       c.created_at, c.updated_at,
       (SELECT COUNT(*) FROM deals d WHERE d.customer_id = c.id) AS deals_total,
       (SELECT COALESCE(SUM(d.amount), 0) FROM deals d
         WHERE d.customer_id = c.id AND d.stage = 'won') AS total_closed_amount
FROM customers c
"""

#: 按标签筛选时追加的 JOIN（UNIQUE(customer_id, tag_id) 保证不会重复出行）
_TAG_JOIN = (
    " INNER JOIN customer_tags ct ON ct.customer_id = c.id"
    " INNER JOIN tags t ON t.id = ct.tag_id"
)

#: PUT 允许改的列（白名单：列名会拼进 SQL，绝不能用客户端传来的 key 直接拼）
_UPDATABLE_COLUMNS = ("name", "phone", "wechat", "location", "house_note")

_RECENT_FOLLOW_UPS_LIMIT = 20


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="客户不存在")


def _like_pattern(term: str) -> str:
    """把用户输入转成 LIKE 模式：转义 ``%``/``_``/``\\``，避免被当通配符。"""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _normalize_tags(names: Iterable[str]) -> list[str]:
    """去空格、丢空值、去重（保序）、限个数。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result[:MAX_TAGS]


def _tags_for(conn, customer_ids: list[int]) -> dict[int, list[str]]:
    """一次查回多个客户的标签，避免列表页 N+1。"""
    if not customer_ids:
        return {}
    placeholders = ", ".join("?" for _ in customer_ids)
    rows = conn.execute(
        f"""
        SELECT ct.customer_id AS customer_id, t.name AS name
        FROM customer_tags ct JOIN tags t ON t.id = ct.tag_id
        WHERE ct.customer_id IN ({placeholders})
        ORDER BY t.name
        """,
        customer_ids,
    ).fetchall()

    grouped: dict[int, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["customer_id"], []).append(row["name"])
    return grouped


def _set_customer_tags(conn, customer_id: int, names: Iterable[str]) -> None:
    """整体替换客户标签：先清旧关联，再把每个名字在 tags 表 upsert 后插入关联。"""
    tags = _normalize_tags(names)
    created_at = now_iso()

    conn.execute("DELETE FROM customer_tags WHERE customer_id = ?", (customer_id,))
    for name in tags:
        conn.execute(
            "INSERT OR IGNORE INTO tags (name, created_at) VALUES (?, ?)",
            (name, created_at),
        )
        tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO customer_tags (customer_id, tag_id) VALUES (?, ?)",
            (customer_id, tag_row["id"]),
        )


def _to_out(row, tags: list[str] | None = None) -> CustomerOut:
    return CustomerOut(**dict(row), tags=tags or [])


@router.get("/customers", response_model=CustomerListOut)
def list_customers(
    search: str | None = Query(default=None, max_length=64, description="姓名/电话/楼盘模糊匹配"),
    tag: str | None = Query(default=None, max_length=32, description="按标签名精确筛选"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> CustomerListOut:
    where_parts: list[str] = []
    params: list[object] = []
    join_sql = ""

    term = (search or "").strip()
    if term:
        pattern = _like_pattern(term)
        where_parts.append(
            "(c.name LIKE ? ESCAPE '\\' "
            "OR c.phone LIKE ? ESCAPE '\\' "
            "OR c.location LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, pattern])

    tag_name = (tag or "").strip()
    if tag_name:
        join_sql = _TAG_JOIN
        where_parts.append("t.name = ?")
        params.append(tag_name)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    offset = (page - 1) * size

    with db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM customers c{join_sql} {where_sql}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"{_CUSTOMER_SELECT}{join_sql} {where_sql} ORDER BY c.id DESC LIMIT ? OFFSET ?",
            [*params, size, offset],
        ).fetchall()
        tags_map = _tags_for(conn, [row["id"] for row in rows])

    return CustomerListOut(
        items=[_to_out(row, tags_map.get(row["id"], [])) for row in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/tags", response_model=list[str])
def list_tags() -> list[str]:
    """标签字典（供前端筛选 chips / 输入自动补全）。"""
    with db_conn() as conn:
        rows = conn.execute("SELECT DISTINCT name FROM tags ORDER BY name").fetchall()
    return [row["name"] for row in rows]


@router.post("/customers", response_model=CustomerOut)
def create_customer(payload: CustomerIn) -> CustomerOut:
    now = now_iso()
    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO customers (name, phone, wechat, location, house_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.phone,
                payload.wechat,
                payload.location,
                payload.house_note,
                now,
                now,
            ),
        )
        customer_id = int(cur.lastrowid or 0)
        _set_customer_tags(conn, customer_id, payload.tags)
        row = conn.execute(f"{_CUSTOMER_SELECT} WHERE c.id = ?", (customer_id,)).fetchone()
        tags = _tags_for(conn, [customer_id]).get(customer_id, [])

    return _to_out(row, tags)


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer_id: int) -> CustomerDetailOut:
    with db_conn() as conn:
        row = conn.execute(f"{_CUSTOMER_SELECT} WHERE c.id = ?", (customer_id,)).fetchone()
        if row is None:
            raise _not_found()

        deal_rows = conn.execute(
            "SELECT * FROM deals WHERE customer_id = ? ORDER BY id DESC", (customer_id,)
        ).fetchall()
        follow_rows = conn.execute(
            """
            SELECT id, customer_id, deal_id, content, next_date, created_at
            FROM follow_ups WHERE customer_id = ?
            ORDER BY created_at DESC, id DESC LIMIT ?
            """,
            (customer_id, _RECENT_FOLLOW_UPS_LIMIT),
        ).fetchall()
        tags = _tags_for(conn, [customer_id]).get(customer_id, [])

    out = _to_out(row, tags)
    return CustomerDetailOut(
        **out.model_dump(),
        deals=[DealOut(**dict(r)) for r in deal_rows],
        follow_ups=[FollowUpOut(**dict(r)) for r in follow_rows],
    )


@router.put("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate) -> CustomerOut:
    fields = payload.model_dump(exclude_unset=True)
    # tags 单独处理：传了（哪怕是 [] / null）才替换，没传就不动
    has_tags = "tags" in fields
    tags_payload = fields.pop("tags", None)
    columns = {key: value for key, value in fields.items() if key in _UPDATABLE_COLUMNS}

    with db_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if exists is None:
            raise _not_found()

        if columns:
            assignments = ", ".join(f"{column} = ?" for column in columns)
            conn.execute(
                f"UPDATE customers SET {assignments}, updated_at = ? WHERE id = ?",
                [*columns.values(), now_iso(), customer_id],
            )

        if has_tags:
            _set_customer_tags(conn, customer_id, tags_payload or [])

        row = conn.execute(f"{_CUSTOMER_SELECT} WHERE c.id = ?", (customer_id,)).fetchone()
        tags = _tags_for(conn, [customer_id]).get(customer_id, [])

    return _to_out(row, tags)


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: int) -> dict:
    """删客户；其 deals / follow_ups / customer_tags 由外键级联清掉。"""
    with db_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if exists is None:
            raise _not_found()
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))

    return {"ok": True, "id": customer_id}
