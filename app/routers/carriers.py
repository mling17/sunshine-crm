"""物流公司管理：CRUD + 删除保护。

- Q7：删除物流公司时，如被订单引用 → 409；未被引用 → 允许删除
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import db_conn
from app.models import CarrierIn, CarrierOut, CarrierUpdate
from app.routers.auth import require_auth
from app.security import now_iso
from app.errors import ApiError

router = APIRouter(
    prefix="/api/crm",
    tags=["carriers"],
    dependencies=[Depends(require_auth)],
)


@router.get("/carriers", response_model=List[CarrierOut])
def list_carriers():
    """获取物流公司列表"""
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM carriers ORDER BY id DESC").fetchall()
        return [CarrierOut(**dict(row)) for row in rows]


@router.get("/carriers/{carrier_id}", response_model=CarrierOut)
def get_carrier(carrier_id: int):
    """获取物流公司详情"""
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM carriers WHERE id = ?", (carrier_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="物流公司不存在")
        return CarrierOut(**dict(row))


@router.post("/carriers", response_model=CarrierOut)
def create_carrier(payload: CarrierIn):
    """创建物流公司"""
    with db_conn() as conn:
        now = now_iso()
        cur = conn.execute(
            """
            INSERT INTO carriers 
                (name, code, contact_person, phone, address, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.code,
                payload.contact_person,
                payload.phone,
                payload.address,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM carriers WHERE id = ?", (int(cur.lastrowid or 0),)).fetchone()
        return CarrierOut(**dict(row))


@router.put("/carriers/{carrier_id}", response_model=CarrierOut)
def update_carrier(carrier_id: int, payload: CarrierUpdate):
    """更新物流公司"""
    with db_conn() as conn:
        # 检查物流公司是否存在
        row = conn.execute("SELECT * FROM carriers WHERE id = ?", (carrier_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="物流公司不存在")
            
        # 更新物流公司信息
        conn.execute(
            """
            UPDATE carriers 
            SET name = ?, code = ?, contact_person = ?, phone = ?, address = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.name,
                payload.code,
                payload.contact_person,
                payload.phone,
                payload.address,
                now_iso(),
                carrier_id,
            ),
        )
        
        # 获取更新后的物流公司
        updated_row = conn.execute("SELECT * FROM carriers WHERE id = ?", (carrier_id,)).fetchone()
        return CarrierOut(**dict(updated_row))


@router.delete("/carriers/{carrier_id}", response_model=dict)
def delete_carrier(carrier_id: int):
    """删除物流公司"""
    with db_conn() as conn:
        # 检查物流公司是否存在
        row = conn.execute("SELECT * FROM carriers WHERE id = ?", (carrier_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="物流公司不存在")
            
        # 检查是否有订单引用该物流公司
        referenced = conn.execute(
            "SELECT COUNT(*) as count FROM orders WHERE carrier_id = ?",
            (carrier_id,)
        ).fetchone()
        
        if referenced[0] > 0:
            raise ApiError(
                status_code=409,
                code="carrier_referenced",
                message="物流公司已被订单引用，无法删除"
            )
            
        # 删除物流公司
        conn.execute("DELETE FROM carriers WHERE id = ?", (carrier_id,))
        return {"message": "删除成功"}