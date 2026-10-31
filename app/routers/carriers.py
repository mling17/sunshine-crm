"""物流公司管理：CRUD + 多联系人 + 删除保护（PLANNER-V3 §5.8）。

- 一个物流公司可有多个联系人（姓名/电话/标签），整组覆盖式保存；
- 被订单引用 → 409 carrier_in_use，只能停用不能删除；
- `order_count` 实时算，不落库。
"""
from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.db import db_conn
from app.errors import ApiError
from app.models import CarrierIn, CarrierOut, CarrierUpdate
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


@router.get("/carriers", response_model=List[CarrierOut])
def list_carriers():
    """物流公司列表（含联系人 + 被引用次数）。"""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM carriers WHERE is_delete = 0 ORDER BY id DESC"
        ).fetchall()
        return [CarrierOut(**_pack(conn, row)) for row in rows]


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
