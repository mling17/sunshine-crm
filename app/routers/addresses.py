"""客户地址簿（PLANNER-V3 §5.4）—— 下单可选历史地址，手填的新地址回存这里。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.db import db_conn
from app.errors import ApiError
from app.routers.auth import require_auth
from app.security import now_iso

router = APIRouter(
    prefix="/api/crm",
    tags=["addresses"],
    dependencies=[Depends(require_auth)],
)

_COLUMNS = "id, customer_id, label, receiver_name, phone, address, is_default, created_at, updated_at"


def _row(conn, customer_id: int, address_id: int):
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM customer_addresses"
        " WHERE id = ? AND customer_id = ? AND is_delete = 0",
        (address_id, customer_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="地址不存在")
    return dict(row)


def _clean(payload: dict) -> dict:
    out = {
        "label": (payload.get("label") or "").strip() or None,
        "receiver_name": (payload.get("receiver_name") or "").strip(),
        "phone": (payload.get("phone") or payload.get("receiver_phone") or "").strip(),
        "address": (payload.get("address") or payload.get("receiver_address") or "").strip(),
    }
    if not out["receiver_name"] or not out["phone"] or not out["address"]:
        raise ApiError(
            status_code=400,
            code="address_incomplete",
            message="收货人 / 电话 / 地址都要填",
        )
    return out


@router.get("/customers/{customer_id}/addresses")
def list_addresses(customer_id: int) -> list[dict]:
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM customer_addresses"
            " WHERE customer_id = ? AND is_delete = 0"
            " ORDER BY is_default DESC, id DESC",
            (customer_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/customers/{customer_id}/addresses")
def create_address(customer_id: int, payload: dict) -> dict:
    data = _clean(payload)
    with db_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND is_delete = 0", (customer_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="客户不存在")
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO customer_addresses (customer_id, label, receiver_name, phone, address,"
            " is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                customer_id,
                data["label"],
                data["receiver_name"],
                data["phone"],
                data["address"],
                1 if payload.get("is_default") else 0,
                now,
                now,
            ),
        )
        address_id = int(cur.lastrowid or 0)
        if payload.get("is_default"):
            conn.execute(
                "UPDATE customer_addresses SET is_default = 0"
                " WHERE customer_id = ? AND id <> ? AND is_delete = 0",
                (customer_id, address_id),
            )
        return _row(conn, customer_id, address_id)


@router.put("/customers/{customer_id}/addresses/{address_id}")
def update_address(customer_id: int, address_id: int, payload: dict) -> dict:
    with db_conn() as conn:
        _row(conn, customer_id, address_id)
        sets, values = [], []
        for field in ("label", "receiver_name", "address"):
            if field in payload:
                sets.append(f"{field} = ?")
                values.append((payload[field] or "").strip() or None)
        if "phone" in payload or "receiver_phone" in payload:
            sets.append("phone = ?")
            values.append((payload.get("phone") or payload.get("receiver_phone") or "").strip())
        if "is_default" in payload:
            sets.append("is_default = ?")
            values.append(1 if payload["is_default"] else 0)
        if not sets:
            raise ApiError(status_code=400, code="nothing_to_update", message="没有要更新的字段")
        conn.execute(
            f"UPDATE customer_addresses SET {', '.join(sets)}, updated_at = ?"
            " WHERE id = ? AND customer_id = ? AND is_delete = 0",
            [*values, now_iso(), address_id, customer_id],
        )
        if payload.get("is_default"):
            conn.execute(
                "UPDATE customer_addresses SET is_default = 0"
                " WHERE customer_id = ? AND id <> ? AND is_delete = 0",
                (customer_id, address_id),
            )
        return _row(conn, customer_id, address_id)


@router.delete("/customers/{customer_id}/addresses/{address_id}")
def delete_address(customer_id: int, address_id: int) -> dict:
    with db_conn() as conn:
        _row(conn, customer_id, address_id)
        # 历史订单存的是快照 + address_id（FK ON DELETE SET NULL），删地址不影响已下单信息
        conn.execute(
            "UPDATE orders SET address_id = NULL WHERE address_id = ?", (address_id,)
        )
        conn.execute(
            "UPDATE customer_addresses SET is_delete = 1,"
            " update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            " WHERE id = ? AND customer_id = ? AND is_delete = 0",
            (address_id, customer_id),
        )
    return {"id": address_id, "deleted": True}
