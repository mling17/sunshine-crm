"""客户档案：CRUD + 搜索分页 + 详情（含商机/最近跟进）+ 级联删除。

- 全部接口要求登录（router 级 ``dependencies=[Depends(require_auth)]``）；
- 删除客户靠 DDL 的 ``ON DELETE CASCADE`` 级联清 deals/follow_ups/customer_tags，
  前提是连接上开了 ``PRAGMA foreign_keys=ON``（``app.db.connect`` 已处理）；
- 列表里的 ``deals_total`` / ``total_closed_amount`` 用相关子查询算，避免 N+1。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import db_conn
from app.models import (
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

#: 客户出参里除标签外的固定列（含两个复购口径子查询）
_CUSTOMER_SELECT = """
SELECT c.id, c.name, c.phone, c.wechat, c.location, c.house_note,
       c.created_at, c.updated_at,
       (SELECT COUNT(*) FROM deals d WHERE d.customer_id = c.id) AS deals_total,
       (SELECT COALESCE(SUM(d.amount), 0) FROM deals d
         WHERE d.customer_id = c.id AND d.stage = 'won') AS total_closed_amount
FROM customers c
"""

#: PUT 允许改的列（白名单，列名会拼进 SQL，绝不能用客户端传来的 key 直接拼）
_UPDATABLE_COLUMNS = ("name", "phone", "wechat", "location", "house_note")

_RECENT_FOLLOW_UPS_LIMIT = 20


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="客户不存在")


def _like_pattern(term: str) -> str:
    """把用户输入转成 LIKE 模式：转义 ``%``/``_``/``\\``，避免被当通配符。"""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _to_out(row) -> CustomerOut:
    return CustomerOut(**dict(row))


@router.get("/customers", response_model=CustomerListOut)
def list_customers(
    search: str | None = Query(default=None, max_length=64, description="姓名/电话/楼盘模糊匹配"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> CustomerListOut:
    where_parts: list[str] = []
    params: list[object] = []

    term = (search or "").strip()
    if term:
        pattern = _like_pattern(term)
        where_parts.append(
            "(c.name LIKE ? ESCAPE '\\' "
            "OR c.phone LIKE ? ESCAPE '\\' "
            "OR c.location LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, pattern])

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    offset = (page - 1) * size

    with db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM customers c {where_sql}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"{_CUSTOMER_SELECT} {where_sql} ORDER BY c.id DESC LIMIT ? OFFSET ?",
            [*params, size, offset],
        ).fetchall()

    return CustomerListOut(
        items=[_to_out(row) for row in rows], total=total, page=page, size=size
    )


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
        row = conn.execute(f"{_CUSTOMER_SELECT} WHERE c.id = ?", (customer_id,)).fetchone()

    return _to_out(row)


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

    out = _to_out(row)
    return CustomerDetailOut(
        **out.model_dump(),
        deals=[DealOut(**dict(r)) for r in deal_rows],
        follow_ups=[FollowUpOut(**dict(r)) for r in follow_rows],
    )


@router.put("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate) -> CustomerOut:
    fields = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if key in _UPDATABLE_COLUMNS
    }

    with db_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if exists is None:
            raise _not_found()

        if fields:
            assignments = ", ".join(f"{column} = ?" for column in fields)
            conn.execute(
                f"UPDATE customers SET {assignments}, updated_at = ? WHERE id = ?",
                [*fields.values(), now_iso(), customer_id],
            )

        row = conn.execute(f"{_CUSTOMER_SELECT} WHERE c.id = ?", (customer_id,)).fetchone()

    return _to_out(row)


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
