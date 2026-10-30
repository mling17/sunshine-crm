"""订单管理：CRUD + 状态流转。

- 订单状态流：待支付 →(押金+截图)→ 已支付押金 →(财务确认点下一步)→ 生产中 →(尾款+截图)→ 已支付尾款 →(点下一步)→ 待发货 →(物流公司+运单号，自送填"无")→ 已发货 →(确认收货)→ 已完成
- 所有状态变更必须通过 transition() 函数，禁止直接修改 orders.status
- 订单状态校验 + 字段校验 + 单事务 + 日志记录
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.db import db_conn
from app.models import (
    ORDER_STATUS, ORDER_STATUS_LABELS, 
    LOGISTICS_MODE, LOGISTICS_MODE_LABELS,
    OrderOut, OrderDetailOut, OrderIn, OrderUpdate,
    AttachmentOut, OrderStatusLogOut
)
from app.routers.auth import require_auth
from app.security import now_iso
from app.errors import ApiError
from app.services import read_images

router = APIRouter(
    prefix="/api/crm",
    tags=["orders"],
    dependencies=[Depends(require_auth)],
)

# 订单状态流转映射
ORDER_TRANSITIONS = {
    "pending_payment": ["deposit_paid"],
    "deposit_paid": ["producing"],
    "producing": ["balance_paid"],
    "balance_paid": ["ready_to_ship"],
    "ready_to_ship": ["shipped"],
    "shipped": ["completed"],
    "completed": [],
}

# 订单状态对应的需要的字段
STATUS_REQUIRED_FIELDS = {
    "deposit_paid": ["deposit", "payment_screenshots"],
    "balance_paid": ["balance", "payment_screenshots"],
    "ready_to_ship": ["logistics_mode", "carrier_id", "tracking_number"],
    "shipped": ["received_at"]
}


class OrderTransitionIn(BaseModel):
    """订单状态转换输入"""
    to_status: ORDER_STATUS
    deposit: Optional[float] = Field(default=None, ge=0)
    balance: Optional[float] = Field(default=None, ge=0)
    payment_screenshots: Optional[List[int]] = Field(default=None)  # 截图附件ID列表
    logistics_mode: Optional[LOGISTICS_MODE] = None
    carrier_id: Optional[int] = Field(default=None, gt=0)
    tracking_number: Optional[str] = Field(default=None, max_length=64)
    received_at: Optional[str] = None  # 确认收货时间
    note: Optional[str] = Field(default=None, max_length=500)


class OrderTransitionOut(BaseModel):
    """订单状态转换输出"""
    order: OrderOut
    status_log: OrderStatusLogOut


@router.get("/orders", response_model=list[OrderOut])
def list_orders(
    customer_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=32),
    deal_id: int | None = Query(default=None, gt=0),
) -> list[OrderOut]:
    """列出订单"""
    where_parts: list[str] = []
    params: list[object] = []

    if customer_id is not None:
        where_parts.append("customer_id = ?")
        params.append(customer_id)

    if status is not None:
        where_parts.append("status = ?")
        params.append(status)

    if deal_id is not None:
        where_parts.append("deal_id = ?")
        params.append(deal_id)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM orders {where_sql} ORDER BY id DESC", params
        ).fetchall()

    return [OrderOut(**dict(row)) for row in rows]


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def get_order(order_id: int) -> OrderDetailOut:
    """获取订单详情"""
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="订单不存在")
        
        # 获取订单状态日志
        status_logs = conn.execute(
            "SELECT * FROM order_status_log WHERE order_id = ? ORDER BY created_at ASC",
            (order_id,)
        ).fetchall()
        
        # 获取附件信息
        attachments = conn.execute(
            "SELECT * FROM attachments WHERE object_type = 'order_payment' AND object_id = ?",
            (order_id,)
        ).fetchall()
        
        # 获取物流公司信息
        carrier_row = None
        if row['carrier_id']:
            carrier_row = conn.execute(
                "SELECT * FROM carriers WHERE id = ?", 
                (row['carrier_id'],)
            ).fetchone()
        
        order_dict = dict(row)
        order_dict['status_logs'] = [OrderStatusLogOut(**dict(log)) for log in status_logs]
        order_dict['attachments'] = [AttachmentOut(**dict(attach)) for attach in attachments]
        order_dict['carrier'] = dict(carrier_row) if carrier_row else None
        
        return OrderDetailOut(**order_dict)


@router.post("/orders", response_model=OrderOut)
def create_order(payload: OrderIn) -> OrderOut:
    """创建订单 - 由于订单必须由商机赢单生成，此接口应返回405"""
    raise HTTPException(status_code=405, detail="订单必须由商机赢单生成")


@router.put("/orders/{order_id}", response_model=OrderOut)
def update_order(order_id: int, payload: OrderUpdate) -> OrderOut:
    """更新订单"""
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="订单不存在")
        
        # 检查是否冻结（订单状态不允许修改）
        # 实际上订单状态由状态转换函数控制，这里只允许修改非状态字段
        updates = payload.model_dump(exclude_unset=True)
        
        # 过滤掉状态字段
        updates.pop('status', None)
        
        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(
                f"UPDATE orders SET {assignments}, updated_at = ? WHERE id = ?",
                [*updates.values(), now_iso(), order_id],
            )
        
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    
    return OrderOut(**dict(row))


@router.post("/orders/{order_id}/transition", response_model=OrderTransitionOut)
def transition_order(order_id: int, payload: OrderTransitionIn) -> OrderTransitionOut:
    """订单状态转换"""
    from app.services import transition
    
    try:
        result = transition(db_conn(), order_id, payload.to_status, payload.dict(exclude_unset=True))
        return OrderTransitionOut(**result)
    except Exception as e:
        if isinstance(e, ApiError):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/pay-deposit", response_model=OrderOut)
def pay_deposit(order_id: int, payload: OrderTransitionIn) -> OrderOut:
    """支付押金"""
    # 验证押金金额
    if payload.deposit is None:
        raise HTTPException(status_code=400, detail="押金金额不能为空")
    
    # 调用状态转换函数
    from app.services import transition
    try:
        result = transition(db_conn(), order_id, "deposit_paid", payload.dict(exclude_unset=True))
        return result["order"]
    except Exception as e:
        if isinstance(e, ApiError):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/pay-balance", response_model=OrderOut)
def pay_balance(order_id: int, payload: OrderTransitionIn) -> OrderOut:
    """支付尾款"""
    # 验证尾款金额
    if payload.balance is None:
        raise HTTPException(status_code=400, detail="尾款金额不能为空")
    
    # 调用状态转换函数
    from app.services import transition
    try:
        result = transition(db_conn(), order_id, "balance_paid", payload.dict(exclude_unset=True))
        return result["order"]
    except Exception as e:
        if isinstance(e, ApiError):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders/{order_id}/status_log", response_model=list[OrderStatusLogOut])
def get_order_status_log(order_id: int) -> list[OrderStatusLogOut]:
    """获取订单状态变更日志"""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM order_status_log WHERE order_id = ? ORDER BY created_at ASC",
            (order_id,)
        ).fetchall()
    
    return [OrderStatusLogOut(**dict(row)) for row in rows]


@router.post("/orders/{order_id}/payment", response_model=OrderOut)
def upload_payment_screenshots(
    order_id: int,
    screenshots: List[UploadFile],
) -> OrderOut:
    """上传支付截图"""
    with db_conn() as conn:
        # 检查订单是否存在
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="订单不存在")
        
        # 读取图片
        try:
            images = read_images(screenshots)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # 保存图片
        attachment_ids = []
        for filename, mime_type, ext, data in images:
            # 保存文件
            from app.storage import save_photo
            url = save_photo(filename, data)
            
            # 插入附件记录
            cur = conn.execute(
                """
                INSERT INTO attachments 
                    (object_type, object_id, file_name, mime_type, size, url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("order_payment", order_id, filename, mime_type, len(data), url, now_iso()),
            )
            attachment_ids.append(int(cur.lastrowid or 0))
        
        # 更新订单
        conn.execute(
            "UPDATE orders SET updated_at = ? WHERE id = ?",
            (now_iso(), order_id)
        )
        
        # 获取更新后的订单
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    
    return OrderOut(**dict(row))