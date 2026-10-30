"""商机管道：CRUD + 阶段流转。

- 阶段合法值统一从 ``app.models.STAGES`` 取，非法值返回 **400**（而不是 pydantic 的 422），
  前端可以统一按 400 提示；
- ``closed_at`` 只在 stage 进入 ``won`` 时写入、从 ``won`` 移出时清空，
  时间用**服务器本地时区**（``security.now_local_iso``），驱动 T6 的「本月成交」；
- 1 客户 N 商机：复购就是在同一客户名下再建一个 deal，商机不允许换客户；
- 商机冻结规则：won/lost 状态下所有写入操作都返回 409。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import db_conn
from app.models import STAGES, DealIn, DealOut, DealUpdate
from app.routers.auth import require_auth
from app.security import now_iso, now_local_iso
from app.errors import ApiError

router = APIRouter(
    prefix="/api/crm",
    tags=["deals"],
    dependencies=[Depends(require_auth)],
)

#: PUT 允许改的列（白名单；customer_id 不在内，商机不从一家挪到另一家）
_UPDATABLE_COLUMNS = ("product_type", "model", "spec", "amount", "deposit", "balance", "stage")

#: 这几列 NOT NULL，显式传 null 必须拒绝，否则 SQL 约束报 500
_REQUIRED_NON_NULL = ("amount", "deposit", "balance", "stage")

#: 商机冻结状态
_FROZEN_STAGES = ("won", "lost")


def _invalid_stage(stage: object) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=f"非法阶段 {stage!r}，合法值：" + "、".join(STAGES),
    )


def _deal_frozen_error() -> ApiError:
    return ApiError(
        status_code=409,
        code="deal_frozen",
        message="商机已赢单/流失，无法修改",
    )


@router.get("/deals", response_model=list[DealOut])
def list_deals(
    customer_id: int | None = Query(default=None, gt=0),
    stage: str | None = Query(default=None, max_length=32),
) -> list[DealOut]:
    where_parts: list[str] = []
    params: list[object] = []

    if customer_id is not None:
        where_parts.append("customer_id = ?")
        params.append(customer_id)

    stage_value = (stage or "").strip()
    if stage_value:
        if stage_value not in STAGES:
            raise _invalid_stage(stage_value)
        where_parts.append("stage = ?")
        params.append(stage_value)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM deals {where_sql} ORDER BY id DESC", params
        ).fetchall()

    return [DealOut(**dict(row)) for row in rows]


@router.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(deal_id: int) -> DealOut:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="商机不存在")
        
        # 检查是否冻结
        if row["stage"] in _FROZEN_STAGES:
            # 冻结状态下，仍然允许获取详情
            pass
            
        return DealOut(**dict(row))


@router.post("/deals", response_model=DealOut)
def create_deal(payload: DealIn) -> DealOut:
    stage = payload.stage.strip()
    if stage not in STAGES:
        raise _invalid_stage(payload.stage)

    now = now_iso()
    closed_at = now_local_iso() if stage == "won" else None

    with db_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM customers WHERE id = ?", (payload.customer_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="客户不存在")

        cur = conn.execute(
            """
            INSERT INTO deals
                (customer_id, product_type, model, spec, amount, deposit, balance,
                 stage, closed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.customer_id,
                payload.product_type,
                payload.model,
                payload.spec,
                payload.amount,
                payload.deposit,
                payload.balance,
                stage,
                closed_at,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM deals WHERE id = ?", (int(cur.lastrowid or 0),)
        ).fetchone()

    return DealOut(**dict(row))


@router.put("/deals/{deal_id}", response_model=DealOut)
def update_deal(deal_id: int, payload: DealUpdate) -> DealOut:
    fields = payload.model_dump(exclude_unset=True)

    for key in _REQUIRED_NON_NULL:
        if key in fields and fields[key] is None:
            raise HTTPException(status_code=400, detail=f"{key} 不能为空")

    if "stage" in fields:
        stage = fields["stage"].strip()
        if stage not in STAGES:
            raise _invalid_stage(fields["stage"])
        fields["stage"] = stage

    with db_conn() as conn:
        row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="商机不存在")

        # 检查是否冻结
        if row["stage"] in _FROZEN_STAGES:
            raise _deal_frozen_error()

        old_stage = row["stage"]
        updates = {key: value for key, value in fields.items() if key in _UPDATABLE_COLUMNS}

        new_stage = updates.get("stage")
        if new_stage is not None and new_stage != old_stage:
            if new_stage == "won":
                updates["closed_at"] = now_local_iso()
            elif old_stage == "won":
                # 从 won 移出（含改为 lost）：成交时间作废，避免统计虚高
                updates["closed_at"] = None

        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(
                f"UPDATE deals SET {assignments}, updated_at = ? WHERE id = ?",
                [*updates.values(), now_iso(), deal_id],
            )

        row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()

    return DealOut(**dict(row))


@router.post("/deals/{deal_id}/win", response_model=dict)
def win_deal(deal_id: int) -> dict:
    """商机赢单，生成订单"""
    from app.services import next_no
    
    with db_conn() as conn:
        # 1. 检查商机是否存在
        deal = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if deal is None:
            raise HTTPException(status_code=404, detail="商机不存在")
            
        # 2. 检查是否已冻结
        if deal["stage"] in _FROZEN_STAGES:
            raise _deal_frozen_error()
            
        # 3. 检查是否已有订单
        existing_order = conn.execute(
            "SELECT 1 FROM orders WHERE deal_id = ?", (deal_id,)
        ).fetchone()
        if existing_order:
            raise ApiError(
                status_code=409,
                code="order_exists",
                message="该商机已有订单",
            )
            
        # 4. 检查金额是否有效
        if deal["amount"] <= 0:
            raise HTTPException(
                status_code=400,
                detail="商机金额必须大于0",
            )
            
        # 5. 生成订单号
        order_no = next_no(conn, "orders", "order_no", "SO", now_local_iso()[:8])
        
        # 6. 创建订单（事务内）
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            # 创建订单
            cur = conn.execute(
                """
                INSERT INTO orders 
                    (order_no, customer_id, deal_id, product_type, model, spec, 
                     amount, status, owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_no,
                    deal["customer_id"],
                    deal_id,
                    deal["product_type"],
                    deal["model"],
                    deal["spec"],
                    deal["amount"],
                    "pending_payment",
                    deal["owner"] if deal["owner"] else None,
                    now_iso(),
                    now_iso(),
                ),
            )
            order_id = int(cur.lastrowid or 0)
            
            # 更新商机状态
            conn.execute(
                """
                UPDATE deals 
                SET stage = 'won', closed_at = ?, order_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    now_local_iso(),
                    order_id,
                    now_iso(),
                    deal_id,
                ),
            )
            
            # 插入订单状态日志
            conn.execute(
                """
                INSERT INTO order_status_log 
                    (order_id, from_status, to_status, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    None,
                    "pending_payment",
                    "商机赢单生成订单",
                    now_iso(),
                ),
            )
            
            conn.commit()
        except Exception:
            conn.rollback()
            raise
            
        # 7. 返回结果
        deal_row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        
        return {
            "deal": DealOut(**dict(deal_row)),
            "order": order_row
        }


@router.post("/deals/{deal_id}/lose", response_model=DealOut)
def lose_deal(deal_id: int, payload: dict) -> DealOut:
    """商机流失"""
    lost_reason = payload.get("lost_reason")
    lost_reason_other = payload.get("lost_reason_other")
    
    # 验证流失原因
    from app.enums import DEAL_LOST_REASON
    if not lost_reason:
        raise HTTPException(status_code=400, detail="流失原因不能为空")
    
    # 检查是否是有效的流失原因
    if lost_reason not in DEAL_LOST_REASON.__args__:
        raise HTTPException(status_code=400, detail="无效的流失原因")
        
    # 如果是other，需要提供其他说明
    if lost_reason == "other" and not lost_reason_other:
        raise HTTPException(status_code=400, detail="其他流失原因不能为空")
    
    with db_conn() as conn:
        # 1. 检查商机是否存在
        deal = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if deal is None:
            raise HTTPException(status_code=404, detail="商机不存在")
            
        # 2. 检查是否已冻结
        if deal["stage"] in _FROZEN_STAGES:
            raise _deal_frozen_error()
            
        # 3. 更新商机状态
        conn.execute(
            """
            UPDATE deals 
            SET stage = 'lost', lost_reason = ?, lost_reason_other = ?, closed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                lost_reason,
                lost_reason_other,
                now_iso(),
                deal_id,
            ),
        )
        
        row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        
    return DealOut(**dict(row))
