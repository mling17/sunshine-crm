"""
售后单管理：建单、处理、完成、拒绝。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import IntegrityError, db_conn
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

_AFTERSALE_SELECT = """
    SELECT a.id, a.no, a.order_id, a.customer_id, a.type, a.type_other,
           a.description, a.status, a.reject_reason, a.result, a.closed_at,
           a.created_at, a.updated_at, a.related_aftersale_id,
           o.order_no, c.name AS customer_name,
           ra.no AS related_aftersale_no,
           ra.status AS related_aftersale_status
      FROM aftersales a
      JOIN orders o ON o.id = a.order_id
      JOIN customers c ON c.id = a.customer_id
      LEFT JOIN aftersales ra
        ON ra.id = a.related_aftersale_id AND ra.is_delete = 0
"""


def _aftersale_out(row) -> AftersaleOut:
    return AftersaleOut(
        id=row["id"],
        no=row["no"],
        order_id=row["order_id"],
        customer_id=row["customer_id"],
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
        customer_name=row["customer_name"],
        related_aftersale_id=row["related_aftersale_id"],
        related_aftersale_no=row["related_aftersale_no"],
        related_aftersale_status=row["related_aftersale_status"],
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
        # 检查订单是否存在 + 必须已完成才能报售后（PLANNER-V3 §5.8）
        order = conn.execute(
            "SELECT id, status, customer_id FROM orders WHERE id = ? AND is_delete = 0",
            (payload.order_id,),
        ).fetchone()
        if not order:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="order_not_found",
                message="订单不存在"
            )
        if order["status"] != "completed":
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="order_not_completed",
                message="订单完成后才能添加售后",
            )

        if payload.related_aftersale_id is not None:
            related = conn.execute(
                """
                SELECT id, order_id, status
                  FROM aftersales
                 WHERE id = ? AND is_delete = 0
                """,
                (payload.related_aftersale_id,),
            ).fetchone()
            if not related:
                raise ApiError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="related_aftersale_not_found",
                    message="关联的历史售后单不存在",
                )
            if int(related["order_id"]) != int(payload.order_id):
                raise ApiError(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="related_aftersale_order_mismatch",
                    message="只能关联当前订单下的历史售后单",
                )
            if related["status"] != "done":
                raise ApiError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="related_aftersale_not_completed",
                    message="只能关联已完成的历史售后单",
                )
        
        # 生成售后单号
        day = datetime.now().strftime("%Y%m%d")
        no = next_no(conn, "aftersales", "no", "AS", day)
        
        # 获取订单对应的客户ID
        customer_id = order["customer_id"]
        now = datetime.now().isoformat()
        
        # 插入售后单
        try:
            cur = conn.execute(
                """
                INSERT INTO aftersales (no, order_id, customer_id, type, type_other, 
                                       description, status, related_aftersale_id,
                                       created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    no,
                    payload.order_id,
                    customer_id,
                    payload.type,
                    payload.type_other,
                    payload.description,
                    "pending",
                    payload.related_aftersale_id,
                    now,
                    now,
                )
            )
        except IntegrityError:
            # 并发冲突，重试一次
            conn.rollback()
            no = next_no(conn, "aftersales", "no", "AS", day)
            cur = conn.execute(
                """
                INSERT INTO aftersales (no, order_id, customer_id, type, type_other, 
                                       description, status, related_aftersale_id,
                                       created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    no,
                    payload.order_id,
                    customer_id,
                    payload.type,
                    payload.type_other,
                    payload.description,
                    "pending",
                    payload.related_aftersale_id,
                    now,
                    now,
                )
            )

        from app.timeline import add_entry

        add_entry(
            conn,
            object_type="aftersale",
            object_id=int(cur.lastrowid or 0),
            kind="create",
            content=(
                "创建售后单"
                + (f"（关联历史售后 #{payload.related_aftersale_id}）"
                   if payload.related_aftersale_id else "")
            ),
        )
        conn.commit()
        
        # 查询返回结果
        row = conn.execute(
            _AFTERSALE_SELECT + " WHERE a.id = ?",
            (int(cur.lastrowid or 0),),
        ).fetchone()
        
        return _aftersale_out(row)


@router.get("/{id}", response_model=AftersaleDetailOut)
def get_aftersale_detail(id: int) -> AftersaleDetailOut:
    """获取售后单详情"""
    with db_conn() as conn:
        # 查询售后单基础信息
        row = conn.execute(
            _AFTERSALE_SELECT + " WHERE a.id = ?",
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
        
        from app.timeline import entries_for

        timeline = entries_for(conn, object_type="aftersale", object_id=id)
        materials = [
            f for entry in timeline if entry.get("type") == "follow" for f in entry.get("files", [])
        ]
        return AftersaleDetailOut(
            timeline=timeline,
            materials=materials,
            id=row["id"],
            no=row["no"],
            order_id=row["order_id"],
            customer_id=row["customer_id"],
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
            customer_name=row["customer_name"],
            related_aftersale_id=row["related_aftersale_id"],
            related_aftersale_no=row["related_aftersale_no"],
            related_aftersale_status=row["related_aftersale_status"],
            status_logs=status_logs,
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
        data_query = (
            _AFTERSALE_SELECT
            + f" {where_clause}"
            + " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        )
        rows = conn.execute(data_query, params + [size, offset]).fetchall()
        
        items = [_aftersale_out(row) for row in rows]
        
        return AftersaleListOut(
            items=items,
            total=total,
            page=page,
            size=size
        )


@router.post("/{id}/start", response_model=dict)
def start_aftersale_deprecated(id: int) -> dict:
    """已下线（PLANNER-V3 §6.4）：保留路由只为给旧前端明确提示，不落库。"""
    raise ApiError(status_code=410, code="deprecated", message="该操作已下线：记一条跟进后会自动进入「处理中」")

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
            "INSERT INTO aftersale_status_log (aftersale_id, from_status, to_status, note, created_at)"
            " VALUES (?, 'processing', 'done', ?, ?)",
            (id, payload.result, datetime.now().isoformat()),
        )
        # 履历（PLANNER-V3 §3.5：售后完成写 kind='stage'）
        from app.timeline import add_entry

        add_entry(
            conn,
            object_type="aftersale",
            object_id=id,
            kind="stage",
            content=f"状态变更：处理中 → 已完成（{payload.result}）",
            detail={"from": "processing", "to": "done"},
        )
        
        conn.commit()
        
        # 查询返回结果
        row = conn.execute(
            _AFTERSALE_SELECT + " WHERE a.id = ?",
            (id,)
        ).fetchone()
        
        return _aftersale_out(row)


@router.post("/{id}/reject", response_model=dict)
def reject_aftersale_deprecated(id: int) -> dict:
    """已下线（PLANNER-V3 §6.4）：保留路由只为给旧前端明确提示，不落库。"""
    raise ApiError(status_code=410, code="deprecated", message="售后不再支持「拒绝」：待处理只保留自动流转，完成请用「标记完成」")

