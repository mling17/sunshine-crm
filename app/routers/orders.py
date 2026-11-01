"""订单管理：CRUD + 状态流转。

- 订单状态流：待支付 →(定金+截图)→ 已支付定金 →(财务确认点下一步)→ 生产中 →(尾款+截图)→ 已支付尾款 →(点下一步)→ 待发货 →(物流公司+运单号，自送填"无")→ 已发货 →(确认收货)→ 已完成
- 所有状态变更必须通过 transition() 函数，禁止直接修改 orders.status
- 订单状态校验 + 字段校验 + 单事务 + 日志记录
"""
from __future__ import annotations

from typing import Optional, List
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.db import db_conn
from app.models import (
    ORDER_STATUS, ORDER_STATUS_LABELS,
    LOGISTICS_MODE, LOGISTICS_MODE_LABELS,
    OrderOut, OrderDetailOut, OrderIn, OrderUpdate,
    AttachmentOut, OrderStatusLogOut, OrderTransitionIn, OrderTransitionOut
)
from app.routers.auth import require_auth
from app.timeline import add_entry, entries_for
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
    "pending_confirmation": ["pending_payment"],
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
        result = []
        for row in rows:
            data = dict(row)
            count_row = conn.execute(
                "SELECT COUNT(*) AS n FROM order_items"
                " WHERE order_id = ? AND is_delete = 0",
                (row["id"],),
            ).fetchone()
            data["item_count"] = int(count_row["n"] or 0)
            result.append(OrderOut(**data))

    return result


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
        order_dict["freight_amount"] = float(order_dict.get("logistics_fee") or 0)
        order_dict["logistics_mode_label"] = LOGISTICS_MODE_LABELS.get(
            order_dict.get("logistics_mode")
        )
        order_dict['status_log'] = [OrderStatusLogOut(**dict(log)) for log in status_logs]
        order_dict['attachments'] = [AttachmentOut(**dict(attach)) for attach in attachments]
        order_dict['carrier'] = dict(carrier_row) if carrier_row else None
        order_dict["items"] = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM order_items WHERE order_id = ? AND is_delete = 0"
                " ORDER BY sort, id",
                (order_id,),
            ).fetchall()
        ]
        order_dict["item_count"] = len(order_dict["items"])
        order_dict["confirmation_files"] = [
            AttachmentOut(**dict(attach))
            for attach in conn.execute(
                "SELECT * FROM attachments"
                " WHERE object_type = 'order_confirmation' AND object_id = ?"
                " ORDER BY id",
                (order_id,),
            ).fetchall()
        ]

        # 物流联系人（多联系人 + 标签）
        if row['carrier_id']:
            order_dict['carrier_contacts'] = [
                {"id": c["id"], "name": c["name"], "phone": c["phone"],
                 "tags": json.loads(c["tags"]) if c["tags"] else []}
                for c in conn.execute(
                    "SELECT id, name, phone, tags FROM carrier_contacts"
                    " WHERE carrier_id = ? ORDER BY sort, id", (row['carrier_id'],)
                ).fetchall()
            ]
        # 售后单（没有就是空列表，前端整块隐藏）
        order_dict['aftersales'] = [
            dict(a) for a in conn.execute(
                "SELECT id, no, type, status, description, result, created_at"
                " FROM aftersales WHERE order_id = ? ORDER BY id DESC", (order_id,)
            ).fetchall()
        ]
        # 关联商机（可点回）
        deal_row = conn.execute(
            "SELECT id, product_id, product_code_snapshot, product_name_snapshot,"
            " product_config_snapshot, product_type, model, spec, amount, stage, drive_type"
            " FROM deals WHERE id = ?", (row['deal_id'],)
        ).fetchone()
        order_dict['deal'] = dict(deal_row) if deal_row else None
        quote_row = (
            conn.execute(
                "SELECT id, quote_no, title, status, amount, confirmed_at"
                " FROM deal_quotes WHERE id = ? AND is_delete = 0",
                (row["quote_id"],),
            ).fetchone()
            if row["quote_id"]
            else None
        )
        order_dict["quote"] = dict(quote_row) if quote_row else None
        # 订单履历（收款/状态变更/发货/改收货/售后）
        order_dict['timeline'] = entries_for(
            conn, object_type="order", object_id=order_id, include_order_events=True
        )

        return OrderDetailOut(**order_dict)


@router.post("/orders", response_model=OrderOut)
def create_order() -> OrderOut:
    """创建订单 —— 订单必须由商机赢单生成（N6），此接口固定 405。"""
    raise ApiError(status_code=405, code="order_create_forbidden", message="订单必须由商机赢单生成")


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
        with db_conn() as conn:
            result = transition(conn, order_id, payload.to_status, payload.model_dump(exclude_unset=True))
        return OrderTransitionOut(**result)
    except Exception as e:
        if isinstance(e, ApiError):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/confirm", response_model=OrderDetailOut)
async def confirm_order(
    order_id: int,
    note: str | None = Form(default=None),
    screenshots: list[UploadFile] = File(default=[]),
) -> OrderDetailOut:
    """记录客户已确认下单表和微信中协商的商务条件。"""
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="订单不存在")
        if row["status"] != "pending_confirmation":
            raise ApiError(
                status_code=409,
                code="order_already_confirmed",
                message="只有「待客户确认」的订单可以执行客户确认",
            )
        if screenshots:
            await _save_order_files(
                conn, order_id, screenshots, object_type="order_confirmation"
            )
        now = now_iso()
        conn.execute(
            "UPDATE orders SET status = 'pending_payment', customer_confirmed_at = ?,"
            " customer_confirmation_note = ?, updated_at = ? WHERE id = ?",
            (now, (note or "").strip() or None, now, order_id),
        )
        conn.execute(
            "INSERT INTO order_status_log"
            " (order_id, from_status, to_status, event_type, note, detail, created_at)"
            " VALUES (?, 'pending_confirmation', 'pending_payment', 'confirm', ?, ?, ?)",
            (
                order_id,
                (note or "").strip() or "客户已通过微信确认下单表及协商条件",
                json.dumps({"customer_confirmed_at": now}, ensure_ascii=False),
                now,
            ),
        )
        conn.execute(
            "UPDATE deals SET stage = 'won', closed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["deal_id"]),
        )
        add_entry(
            conn,
            object_type="order",
            object_id=order_id,
            kind="confirm",
            customer_id=row["customer_id"],
            deal_id=row["deal_id"],
            content=(note or "").strip() or "客户已通过微信确认下单表及协商条件",
            detail={"from_status": "pending_confirmation", "to_status": "pending_payment"},
        )
        add_entry(
            conn,
            object_type="deal",
            object_id=row["deal_id"],
            kind="confirm",
            customer_id=row["customer_id"],
            deal_id=row["deal_id"],
            content=f"客户已确认订单 {row['order_no']}",
            detail={"order_id": order_id},
        )
    return get_order(order_id)


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
                    (object_type, object_id, file_name, mime_type, size, storage_key, created_at)
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

# ---------------- 前端契约：定金 / 尾款支付（multipart） ----------------
async def _save_order_files(
    conn, order_id: int, screenshots, *, object_type: str = "order_payment"
) -> list[int]:
    """存订单截图/确认凭证到 attachments。async：UploadFile.read 是协程。"""
    from app.storage import MAX_PHOTO_BYTES, ext_and_mime, new_storage_key, save_photo

    ids: list[int] = []
    prepared = []
    for uf in screenshots or []:
        data = await uf.read()
        if not data and not getattr(uf, "filename", ""):
            continue
        ext, mime = ext_and_mime(getattr(uf, "filename", None), getattr(uf, "content_type", None))
        if not data:
            raise HTTPException(status_code=400, detail=f"截图 {getattr(uf, 'filename', '')} 是空文件")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=400, detail=f"截图超过 {MAX_PHOTO_BYTES // (1024 * 1024)}MB")
        prepared.append((getattr(uf, "filename", "") or f"shot{ext}", mime, ext, data))
    for file_name, mime, ext, data in prepared:
        key = new_storage_key(ext)
        save_photo(key, data)
        cur = conn.execute(
            """INSERT INTO attachments
                 (object_type, object_id, file_name, mime_type, size, storage_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (object_type, order_id, file_name, mime, len(data), key, now_iso()),
        )
        ids.append(int(cur.lastrowid or 0))
    return ids


@router.post("/orders/{order_id}/pay-deposit", response_model=OrderTransitionOut)
async def pay_deposit(
    order_id: int,
    amount: float = Form(..., description="定金金额"),
    note: str | None = Form(default=None),
    screenshots: list[UploadFile] = File(default=[]),
) -> OrderTransitionOut:
    from app.services import transition

    with db_conn() as conn:
        if screenshots:
            await _save_order_files(conn, order_id, screenshots)
        result = transition(conn, order_id, "deposit_paid", {"deposit": amount, "note": note})
    return OrderTransitionOut(**result)


@router.post("/orders/{order_id}/pay-balance", response_model=OrderTransitionOut)
async def pay_balance(
    order_id: int,
    amount: float = Form(..., description="尾款金额（必须等于总额-已收定金）"),
    note: str | None = Form(default=None),
    screenshots: list[UploadFile] = File(default=[]),
) -> OrderTransitionOut:
    from app.services import transition

    with db_conn() as conn:
        if screenshots:
            await _save_order_files(conn, order_id, screenshots)
        result = transition(conn, order_id, "balance_paid", {"balance": amount, "note": note})
    return OrderTransitionOut(**result)
