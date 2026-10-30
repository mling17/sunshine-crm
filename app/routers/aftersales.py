"""
售后单管理：建单、处理、完成、拒绝。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import db_conn
from app.errors import ApiError
from app.models import (
    AftersaleDetailOut,
    AftersaleIn,
    AftersaleOut,
    AftersaleStatusLogOut,
    AftersaleUpdate,
    AftersaleListOut,
)
from app.routers.auth import require_auth
from app.services import next_no

router = APIRouter(
    prefix="/api/crm/aftersales",
    tags=["aftersales"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=AftersaleOut)
def create_aftersale(payload: AftersaleIn) -> AftersaleOut:
    """
    新建售后单。
    
    - `order_id`：订单ID（必须存在）
    - `type`：售后类型（退货/换货/维修/投诉/其他）
    - `description`：问题描述（≤2000字符）
    """
    with db_conn() as conn:
        # 检查订单是否存在
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ?", (payload.order_id,)
        ).fetchone()
        if not order:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="order_not_found",
                message="订单不存在"
            )
        
        # 生成售后单号
        day = datetime.now().strftime("%Y%m%d")
        no = next_no(conn, "aftersales", "no", "AS", day)
        
        # 获取订单对应的客户ID
        customer_id = conn.execute(
            "SELECT customer_id FROM orders WHERE id = ?", (payload.order_id,)
        ).fetchone()["customer_id"]
        
        # 插入售后单
        try:
            conn.execute(
                """
                INSERT INTO aftersales (no, order_id, customer_id, type, type_other, 
                                       description, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    no,
                    payload.order_id,
                    customer_id,
                    payload.type,
                    payload.type_other,
                    payload.description,
                    "pending",
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                )
            )
            conn.commit()
        except IntegrityError:
            # 并发冲突，重试一次
            conn.rollback()
            no = next_no(conn, "aftersales", "no", "AS", day)
            conn.execute(
                """
                INSERT INTO aftersales (no, order_id, customer_id, type, type_other, 
                                       description, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    no,
                    payload.order_id,
                    customer_id,
                    payload.type,
                    payload.type_other,
                    payload.description,
                    "pending",
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                )
            )
            conn.commit()
        
        # 查询返回结果
        row = conn.execute(
            """
            SELECT a.id, a.no, a.type, a.type_other, a.description, a.status, 
                   a.reject_reason, a.result, a.closed_at, a.created_at, a.updated_at,
                   o.order_no, c.name AS customer_name
            FROM aftersales a
            JOIN orders o ON o.id = a.order_id
            JOIN customers c ON c.id = a.customer_id
            WHERE a.no = ?
            """,
            (no,)
        ).fetchone()
        
        return AftersaleOut(
            id=row["id"],
            no=row["no"],
            type=row["type"],
            type_other=row["type_other"],
            description=row["description"],
            status=row["status"],
            reject_reason=row["reject_reason"],
            result=row["result"],
            closed_at=row["closed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            order_no=row["order_no"],
            customer_name=row["customer_name"]
        )


@router.get("/{id}", response_model=AftersaleDetailOut)
def get_aftersale_detail(id: int) -> AftersaleDetailOut:
    """获取售后单详情"""
    with db_conn() as conn:
        # 查询售后单基础信息
        row = conn.execute(
            """
            SELECT a.id, a.no, a.type, a.type_other, a.description, a.status, 
                   a.reject_reason, a.result, a.closed_at, a.created_at, a.updated_at,
                   o.id AS order_id, o.order_no, c.name AS customer_name
            FROM aftersales a
            JOIN orders o ON o.id = a.order_id
            JOIN customers c ON c.id = a.customer_id
            WHERE a.id = ?
            """,
            (id,)
        ).fetchone()
        
        if not row:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="aftersale_not_found",
                message="售后单不存在"
            )
        
        # 查询状态日志
        status_logs = []
        for log_row in conn.execute(
            """
            SELECT id, from_status, to_status, note, created_at
            FROM aftersale_status_log
            WHERE aftersale_id = ?
            ORDER BY created_at ASC
            """,
            (id,)
        ).fetchall():
            status_logs.append(AftersaleStatusLogOut(
                id=log_row["id"],
                from_status=log_row["from_status"],
                to_status=log_row["to_status"],
                note=log_row["note"],
                created_at=log_row["created_at"]
            ))
        
        return AftersaleDetailOut(
            id=row["id"],
            no=row["no"],
            type=row["type"],
            type_other=row["type_other"],
            description=row["description"],
            status=row["status"],
            reject_reason=row["reject_reason"],
            result=row["result"],
            closed_at=row["closed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            order_id=row["order_id"],
            order_no=row["order_no"],
            customer_name=row["customer_name"],
            status_log=status_logs
        )


@router.get("", response_model=AftersaleListOut)
def list_aftersales(
    status: Optional[str] = None,
    order_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    sla_overdue: Optional[bool] = None,
    page: int = 1,
    size: int = 20
) -> AftersaleListOut:
    """获取售后单列表"""
    with db_conn() as conn:
        # 构建查询条件
        conditions = []
        params = []
        
        if status:
            conditions.append("a.status = ?")
            params.append(status)
            
        if order_id:
            conditions.append("a.order_id = ?")
            params.append(order_id)
            
        if customer_id:
            conditions.append("a.customer_id = ?")
            params.append(customer_id)
            
        if sla_overdue is not None:
            if sla_overdue:
                conditions.append(
                    "a.status = 'pending' AND julianday(date('now','localtime')) - julianday(date(a.created_at)) > 3"
                )
            else:
                conditions.append(
                    "a.status = 'pending' AND julianday(date('now','localtime')) - julianday(date(a.created_at)) <= 3"
                )
        
        where_clause = " AND ".join(conditions) if conditions else ""
        if where_clause:
            where_clause = "WHERE " + where_clause
            
        # 查询总数
        count_query = f"""
            SELECT COUNT(*) AS total
            FROM aftersales a
            {where_clause}
        """
        total = conn.execute(count_query, params).fetchone()["total"]
        
        # 查询分页数据
        offset = (page - 1) * size
        data_query = f"""
            SELECT a.id, a.no, a.type, a.type_other, a.description, a.status, 
                   a.reject_reason, a.result, a.closed_at, a.created_at, a.updated_at,
                   o.order_no, c.name AS customer_name
            FROM aftersales a
            JOIN orders o ON o.id = a.order_id
            JOIN customers c ON c.id = a.customer_id
            {where_clause}
            ORDER BY a.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(data_query, params + [size, offset]).fetchall()
        
        items = [
            AftersaleOut(
                id=row["id"],
                no=row["no"],
                type=row["type"],
                type_other=row["type_other"],
                description=row["description"],
                status=row["status"],
                reject_reason=row["reject_reason"],
                result=row["result"],
                closed_at=row["closed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                order_no=row["order_no"],
                customer_name=row["customer_name"]
            )
            for row in rows
        ]
        
        return AftersaleListOut(
            items=items,
            total=total,
            page=page,
            size=size
        )


@router.post("/{id}/start", response_model=AftersaleOut)
def start_aftersale(id: int) -> AftersaleOut:
    """开始处理售后单"""
    with db_conn() as conn:
        # 检查售后单是否存在
        aftersale = conn.execute(
            "SELECT id, status FROM aftersales WHERE id = ?", (id,)
        ).fetchone()
        
        if not aftersale:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="aftersale_not_found",
                message="售后单不存在"
            )
        
        # 检查状态是否可以开始处理
        if aftersale["status"] != "pending":
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="illegal_transition",
                message="售后单状态不允许开始处理",
                current_status=aftersale["status"]
            )
        
        # 更新状态为处理中
        conn.execute(
            "UPDATE aftersales SET status = 'processing', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), id)
        )
        
        # 记录状态日志
        conn.execute(
            """
            INSERT INTO aftersale_status_log (aftersale_id, from_status, to_status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (id, "pending", "processing", datetime.now().isoformat())
        )
        
        conn.commit()
        
        # 查询返回结果
        row = conn.execute(
            """
            SELECT a.id, a.no, a.type, a.type_other, a.description, a.status, 
                   a.reject_reason, a.result, a.closed_at, a.created_at, a.updated_at,
                   o.order_no, c.name AS customer_name
            FROM aftersales a
            JOIN orders o ON o.id = a.order_id
            JOIN customers c ON c.id = a.customer_id
            WHERE a.id = ?
            """,
            (id,)
        ).fetchone()
        
        return AftersaleOut(
            id=row["id"],
            no=row["no"],
            type=row["type"],
            type_other=row["type_other"],
            description=row["description"],
            status=row["status"],
            reject_reason=row["reject_reason"],
            result=row["result"],
            closed_at=row["closed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            order_no=row["order_no"],
            customer_name=row["customer_name"]
        )


@router.post("/{id}/finish", response_model=AftersaleOut)
def finish_aftersale(id: int, payload: AftersaleUpdate) -> AftersaleOut:
    """完成售后单"""
    if not payload.result:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="result_required",
            message="完成售后单必须填写处理结果"
        )
        
    with db_conn() as conn:
        # 检查售后单是否存在
        aftersale = conn.execute(
            "SELECT id, status FROM aftersales WHERE id = ?", (id,)
        ).fetchone()
        
        if not aftersale:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="aftersale_not_found",
                message="售后单不存在"
            )
        
        # 检查状态是否可以完成
        if aftersale["status"] != "processing":
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="illegal_transition",
                message="售后单状态不允许完成",
                current_status=aftersale["status"]
            )
        
        # 更新状态为已完成
        conn.execute(
            "UPDATE aftersales SET status = 'done', result = ?, closed_at = ?, updated_at = ? WHERE id = ?",
            (payload.result, datetime.now().isoformat(), datetime.now().isoformat(), id)
        )
        
        # 记录状态日志
        conn.execute(
            """
            INSERT INTO aftersale_status_log (aftersale_id, from_status, to_status, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (id, "processing", "done", payload.result, datetime.now().isoformat())
        )
        
        conn.commit()
        
        # 查询返回结果
        row = conn.execute(
            """
            SELECT a.id, a.no, a.type, a.type_other, a.description, a.status, 
                   a.reject_reason, a.result, a.closed_at, a.created_at, a.updated_at,
                   o.order_no, c.name AS customer_name
            FROM aftersales a
            JOIN orders o ON o.id = a.order_id
            JOIN customers c ON c.id = a.customer_id
            WHERE a.id = ?
            """,
            (id,)
        ).fetchone()
        
        return AftersaleOut(
            id=row["id"],
            no=row["no"],
            type=row["type"],
            type_other=row["type_other"],
            description=row["description"],
            status=row["status"],
            reject_reason=row["reject_reason"],
            result=row["result"],
            closed_at=row["closed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            order_no=row["order_no"],
            customer_name=row["customer_name"]
        )


@router.post("/{id}/reject", response_model=AftersaleOut)
def reject_aftersale(id: int, payload: AftersaleUpdate) -> AftersaleOut:
    """拒绝售后单"""
    if not payload.reject_reason:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="reject_reason_required",
            message="拒绝售后单必须填写拒绝原因"
        )
        
    with db_conn() as conn:
        # 检查售后单是否存在
        aftersale = conn.execute(
            "SELECT id, status FROM aftersales WHERE id = ?", (id,)
        ).fetchone()
        
        if not aftersale:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="aftersale_not_found",
                message="售后单不存在"
            )
        
        # 检查状态是否可以拒绝（待处理或处理中都可以拒绝）
        if aftersale["status"] not in ("pending", "processing"):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="illegal_transition",
                message="售后单状态不允许拒绝",
                current_status=aftersale["status"]
            )
        
        # 更新状态为已拒绝
        conn.execute(
            "UPDATE aftersales SET status = 'rejected', reject_reason = ?, closed_at = ?, updated_at = ? WHERE id = ?",
            (payload.reject_reason, datetime.now().isoformat(), datetime.now().isoformat(), id)
        )
        
        # 记录状态日志
        conn.execute(
            """
            INSERT INTO aftersale_status_log (aftersale_id, from_status, to_status, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (id, aftersale["status"], "rejected", payload.reject_reason, datetime.now().isoformat())
        )
        
        conn.commit()
        
        # 查询返回结果
        row = conn.execute(
            """
            SELECT a.id, a.no, a.type, a.type_other, a.description, a.status, 
                   a.reject_reason, a.result, a.closed_at, a.created_at, a.updated_at,
                   o.order_no, c.name AS customer_name
            FROM aftersales a
            JOIN orders o ON o.id = a.order_id
            JOIN customers c ON c.id = a.customer_id
            WHERE a.id = ?
            """,
            (id,)
        ).fetchone()
        
        return AftersaleOut(
            id=row["id"],
            no=row["no"],
            type=row["type"],
            type_other=row["type_other"],
            description=row["description"],
            status=row["status"],
            reject_reason=row["reject_reason"],
            result=row["result"],
            closed_at=row["closed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            order_no=row["order_no"],
            customer_name=row["customer_name"]
        )