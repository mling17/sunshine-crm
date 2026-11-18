"""物流公司管理：CRUD + 多联系人 + 删除保护（PLANNER-V3 §5.8）。

- 一个物流公司可有多个联系人（姓名/电话/标签），整组覆盖式保存；
- 被订单引用 → 409 carrier_in_use，只能停用不能删除；
- `order_count` 实时算，不落库。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import db_conn
from app.errors import ApiError
from app.models import CarrierIn, CarrierListOut, CarrierOut, CarrierUpdate
from app.routers.leads import LIST_PAGE_SIZES
from app.routers.auth import require_auth
from app.security import now_iso

router = APIRouter(
    prefix="/api/crm",
    tags=["carriers"],
    dependencies=[Depends(require_auth)],
)


def _pack(conn, row) -> dict:
    data = dict(row)
    data["is_active"] = bool(data.get("is_active", 1))
    data["contacts"] = [
        {
            "id": c["id"],
            "name": c["name"],
            "phone": c["phone"],
            "tags": json.loads(c["tags"]) if c["tags"] else [],
        }
        for c in conn.execute(
            "SELECT id, name, phone, tags FROM carrier_contacts"
            " WHERE carrier_id = ? AND is_delete = 0 ORDER BY sort, id",
            (row["id"],),
        ).fetchall()
    ]
    data["order_count"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM orders WHERE carrier_id = ? AND is_delete = 0",
            (row["id"],),
        ).fetchone()[0]
    )
    return data


def _save_contacts(conn, carrier_id: int, contacts) -> None:
    """整组覆盖；payload 没带 contacts 就不动。"""
    if contacts is None:
        return
    now = now_iso()
    conn.execute(
        "UPDATE carrier_contacts SET is_delete = 1, update_time = ?"
        " WHERE carrier_id = ? AND is_delete = 0",
        (now, carrier_id),
    )
    for index, item in enumerate(contacts):
        name = str((item or {}).get("name") or "").strip()
        phone = str((item or {}).get("phone") or "").strip()
        if not name or not phone:
            continue
        tags = (item or {}).get("tags") or []
        conn.execute(
            "INSERT INTO carrier_contacts (carrier_id, name, phone, tags, sort, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                carrier_id,
                name,
                phone,
                json.dumps(tags, ensure_ascii=False) if tags else None,
                index,
                now,
                now,
            ),
        )


#: 列表排序白名单（Ticket #15）：排序 SQL 一律来自这里的映射，绝不拼接前端传来的原始列名。
#: name 即「公司名称」列，address 即「地址」列。
_CARRIER_SORT_SQL: dict[str, str] = {
    "name": "c.name",
    "address": "c.address",
}

# 可为 NULL 的排序列：无论升降序都让其沉底（(expr IS NULL) ASC），否则升序时大量空值堆在最前面。
_CARRIER_SORT_NULLABLE = frozenset({"address"})

#: 默认排序（issue #8 物流页口径）：被订单关联次数倒序，稳定次键 id DESC。
#: 该表达式只出现在这里的服务端白名单 SQL 里，绝不接收客户端输入；它是默认排序，不是可排序列。
_ORDER_COUNT_SQL = (
    "(SELECT COUNT(*) FROM orders o WHERE o.carrier_id = c.id AND o.is_delete = 0)"
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/carriers", response_model=CarrierListOut)
def list_carriers(
    q: str | None = Query(default=None, max_length=80),
    active: int | None = Query(default=None, ge=0, le=1),
    page: int = Query(default=1),
    size: int = Query(default=20),
    sort: str | None = Query(default=None),
    order: str = Query(default="desc"),
) -> CarrierListOut:
    """物流公司列表（含联系人 + 被引用次数）。

    分页/排序/筛选（Ticket #15，复用 Ticket #9/#13 同一套校验口径）：size 白名单
    ``LIST_PAGE_SIZES``，sort 白名单见 ``_CARRIER_SORT_SQL``；非法 page/size/sort/order
    一律 400，排序 SQL 只走白名单映射。不传 sort 时按 issue #8 物流页默认口径：
    被订单关联次数倒序，稳定次键 id DESC。关键词匹配公司名/编号/主联系人/电话/地址
    以及多联系人姓名/电话（与原前端本地过滤同口径）；``active`` 仅看启用。
    筛选 -> 排序 -> 分页全部服务端执行。
    """
    if page < 1:
        raise ApiError(status_code=400, code="invalid_page", message="page 必须 >= 1")
    if size not in LIST_PAGE_SIZES:
        raise ApiError(
            status_code=400,
            code="invalid_page_size",
            message=f"size 必须是 {'/'.join(str(s) for s in LIST_PAGE_SIZES)} 之一",
        )
    sort = sort or None  # 显式传空串等同未传，走默认排序
    if sort is not None and sort not in _CARRIER_SORT_SQL:
        raise ApiError(
            status_code=400,
            code="invalid_sort",
            message=f"sort 只支持 {'/'.join(_CARRIER_SORT_SQL)}",
        )
    if order not in ("asc", "desc"):
        raise ApiError(status_code=400, code="invalid_order", message="order 只支持 asc/desc")

    if sort:
        expr = _CARRIER_SORT_SQL[sort]
        dir_sql = "ASC" if order == "asc" else "DESC"
        # 显式排序：稳定次键固定 id DESC；可空列先排 NULL 沉底（升/降序都沉底）。
        if sort in _CARRIER_SORT_NULLABLE:
            order_sql = f"({expr} IS NULL) ASC, {expr} {dir_sql}, c.id DESC"
        else:
            order_sql = f"{expr} {dir_sql}, c.id DESC"
    else:
        order_sql = f"{_ORDER_COUNT_SQL} DESC, c.id DESC"

    where = ["c.is_delete = 0"]
    params: list[object] = []
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        where.append(
            "(c.name LIKE ? ESCAPE '\\' OR c.code LIKE ? ESCAPE '\\'"
            " OR c.contact_person LIKE ? ESCAPE '\\' OR c.phone LIKE ? ESCAPE '\\'"
            " OR c.address LIKE ? ESCAPE '\\'"
            " OR EXISTS (SELECT 1 FROM carrier_contacts cc WHERE cc.carrier_id = c.id"
            " AND cc.is_delete = 0 AND (cc.name LIKE ? ESCAPE '\\' OR cc.phone LIKE ? ESCAPE '\\')))"
        )
        params.extend([like] * 7)
    if active is not None:
        where.append("c.is_active = ?")
        params.append(active)

    where_sql = " AND ".join(where)
    with db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM carriers c WHERE {where_sql}",
            params,
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT c.* FROM carriers c WHERE {where_sql}"
            f" ORDER BY {order_sql} LIMIT ? OFFSET ?",
            [*params, size, (page - 1) * size],
        ).fetchall()
        items = [CarrierOut(**_pack(conn, row)) for row in rows]
    return CarrierListOut(
        items=items,
        total=total,
        page=page,
        size=size,
    )


@router.get("/carriers/{carrier_id}", response_model=CarrierOut)
def get_carrier(carrier_id: int):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM carriers WHERE id = ? AND is_delete = 0", (carrier_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="物流公司不存在")
        return CarrierOut(**_pack(conn, row))


@router.post("/carriers", response_model=CarrierOut)
def create_carrier(payload: CarrierIn):
    with db_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM carriers WHERE name = ? AND is_delete = 0", (payload.name,)
        ).fetchone():
            raise ApiError(
                status_code=409, code="carrier_exists", message=f"物流公司「{payload.name}」已存在"
            )
        now = now_iso()
        contacts = getattr(payload, "contacts", None)
        first = (contacts or [{}])[0] if contacts else {}
        cur = conn.execute(
            "INSERT INTO carriers (name, code, contact_person, phone, address, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload.name,
                payload.code,
                payload.contact_person or first.get("name"),
                payload.phone or first.get("phone"),
                payload.address,
                now,
                now,
            ),
        )
        carrier_id = int(cur.lastrowid or 0)
        _save_contacts(conn, carrier_id, contacts)
        row = conn.execute(
            "SELECT * FROM carriers WHERE id = ? AND is_delete = 0", (carrier_id,)
        ).fetchone()
        return CarrierOut(**_pack(conn, row))


@router.put("/carriers/{carrier_id}", response_model=CarrierOut)
def update_carrier(carrier_id: int, payload: CarrierUpdate):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM carriers WHERE id = ?", (carrier_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="物流公司不存在")

        fields = payload.model_dump(exclude_unset=True)
        contacts = fields.pop("contacts", None)
        # 旧列（主联系人）与 contacts 第 1 条保持同步，V1 出参不乱
        assignments = {k: v for k, v in fields.items()
                       if k in ("name", "code", "contact_person", "phone", "address")}
        # is_active 旧实现漏进 assignments 白名单，停用/启用从未落库（Ticket #15 修掉：
        # 「仅看启用」筛选服务端化后，这个字段必须真的可写）
        if fields.get("is_active") is not None:
            assignments["is_active"] = 1 if fields["is_active"] else 0
        if contacts is not None and contacts:
            assignments.setdefault("contact_person", contacts[0].get("name"))
            assignments.setdefault("phone", contacts[0].get("phone"))
        if assignments:
            sets = ", ".join(f"{k} = ?" for k in assignments)
            conn.execute(
                f"UPDATE carriers SET {sets}, updated_at = ? WHERE id = ?",
                [*assignments.values(), now_iso(), carrier_id],
            )
        _save_contacts(conn, carrier_id, contacts)
        updated = conn.execute(
            "SELECT * FROM carriers WHERE id = ? AND is_delete = 0", (carrier_id,)
        ).fetchone()
        return CarrierOut(**_pack(conn, updated))


@router.delete("/carriers/{carrier_id}", response_model=dict)
def delete_carrier(carrier_id: int):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM carriers WHERE id = ? AND is_delete = 0", (carrier_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="物流公司不存在")

        used = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE carrier_id = ? AND is_delete = 0",
            (carrier_id,),
        ).fetchone()[0]
        if used > 0:
            raise ApiError(
                status_code=409,
                code="carrier_in_use",
                message=f"有 {used} 张订单在用，只能停用不能删除",
            )
        conn.execute(
            "UPDATE carriers SET is_delete = 1,"
            " update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            " WHERE id = ?",
            (carrier_id,),
        )
        return {"message": "删除成功"}
