"""商机 endpoints（PLANNER-V3 §5.5 / §6.2）。

职责边界：
- 这里只做「取参 + 校验 + 错误映射 + 事务编排」；
- 订单号生成走 ``app.services.next_no``，履历写入走 ``app.timeline.add_entry``；
- 金额一律 ``round(x, 2)``；"押金 + 尾款 = 订单金额" 是服务端强制（Q-D 决议）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app import dicts as dict_svc
from app.db import db_conn
from app.enums import (
    DEAL_LOST_REASON,
    DEAL_STAGE_LABELS,
    DEAL_STAGE_ORDER,
    DRIVE_TYPE_LABELS,
    LOGISTICS_MODE_LABELS,
)
from app.errors import ApiError
from app.models import DealDetailOut, DealIn, DealOut, DealUpdate
from app.routers.auth import require_auth
from app.security import now_iso, now_local_iso
from app.services import next_no
from app.timeline import add_entry, change_summary, entries_for

router = APIRouter(
    prefix="/api/crm",
    tags=["deals"],
    dependencies=[Depends(require_auth)],
)

STAGES = DEAL_STAGE_ORDER
#: 会写「编辑」履历的字段
_CHANGE_TRACKED = (
    "product_type", "model", "spec", "drive_type",
    "amount", "deposit", "balance", "note",
)
_UPDATABLE = _CHANGE_TRACKED + ("stage",)
#: 锁定（已生成订单）后唯一允许改的字段
_LOCKED_ALLOWED = ("note",)


# ---------------- 校验小工具 ----------------


def _invalid_stage(value: object) -> ApiError:
    return ApiError(
        status_code=400,
        code="invalid_stage",
        message=f"非法阶段 {value!r}，合法值：" + "、".join(STAGES),
    )


def _deal_locked() -> ApiError:
    return ApiError(
        status_code=409,
        code="deal_locked",
        message="该商机已生成订单，基本信息不可修改（只允许改备注、记跟进）",
    )


def _drive_type(value: object) -> str:
    if not value:
        raise ApiError(status_code=400, code="drive_type_required", message="请选择手动 / 电动")
    text = str(value).strip()
    if text not in DRIVE_TYPE_LABELS:
        raise ApiError(
            status_code=400, code="invalid_drive_type", message="手动 / 电动 只能是 manual 或 electric"
        )
    return text


def _product_type(value: object) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not dict_svc.validate("product_type", text):
        raise ApiError(
            status_code=400,
            code="invalid_product_type",
            message=f"产品类型「{text}」不在数据字典里，请先到数据字典添加",
        )
    return text


def _model(value: object) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not dict_svc.validate("product_model", text):
        raise ApiError(
            status_code=400,
            code="invalid_model",
            message=f"型号「{text}」不在数据字典里，请先到数据字典添加",
        )
    return text


def _spec_from_model(model: str | None) -> str | None:
    if not model:
        return None
    for item in dict_svc.items("product_model"):
        if item["key"] == model:
            return (item.get("meta") or {}).get("size")
    return None


def _deal_row(conn, deal_id: int):
    row = conn.execute(
        "SELECT d.*, c.name AS customer_name FROM deals d"
        " LEFT JOIN customers c ON c.id = d.customer_id"
        " WHERE d.id = ? AND d.is_delete = 0 AND c.is_delete = 0",
        (deal_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="商机不存在")
    return row


def _out(row) -> DealOut:
    data = dict(row)
    data.pop("customer_name", None)
    data["locked"] = data.get("order_id") is not None
    return DealOut(**data)


# ---------------- 列表 / 详情 ----------------


@router.get("/deals", response_model=list[DealOut])
def list_deals(
    customer_id: int | None = Query(default=None, gt=0),
    stage: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=64),
) -> list[DealOut]:
    where, params = ["d.is_delete = 0", "c.is_delete = 0"], []
    if customer_id is not None:
        where.append("d.customer_id = ?")
        params.append(customer_id)
    if stage:
        value = stage.strip()
        if value not in STAGES:
            raise _invalid_stage(value)
        where.append("d.stage = ?")
        params.append(value)
    if q:
        like = f"%{q.strip()}%"
        where.append("(d.model LIKE ? OR d.spec LIKE ? OR c.name LIKE ?)")
        params.extend([like, like, like])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT d.*, c.name AS customer_name FROM deals d"
            f" LEFT JOIN customers c ON c.id = d.customer_id {where_sql}"
            " ORDER BY d.id DESC",
            params,
        ).fetchall()
    return [_out(row) for row in rows]


@router.get("/deals/{deal_id}", response_model=DealDetailOut)
def get_deal(deal_id: int) -> DealDetailOut:
    with db_conn() as conn:
        row = _deal_row(conn, deal_id)
        data = dict(row)
        data["locked"] = data.get("order_id") is not None
        data["timeline"] = entries_for(
            conn, object_type="deal", object_id=deal_id, include_order_events=True
        )
        data["materials"] = [
            f
            for entry in data["timeline"]
            if entry.get("type") == "follow"
            for f in entry.get("files", [])
        ]
        order_row = conn.execute(
            "SELECT * FROM orders WHERE deal_id = ? AND is_delete = 0", (deal_id,)
        ).fetchone()
        data["order"] = dict(order_row) if order_row else None
    return DealDetailOut(**data)


# ---------------- 新建 / 修改 ----------------


@router.post("/deals", response_model=DealOut)
def create_deal(payload: DealIn) -> DealOut:
    with db_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND is_delete = 0",
            (payload.customer_id,),
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="客户不存在")

    drive = _drive_type(payload.drive_type)
    product_type = _product_type(payload.product_type)
    model = _model(payload.model)
    # 定稿：新建阶段固定「报价」
    if payload.stage and payload.stage.strip() not in ("quote", ""):
        raise ApiError(
            status_code=400,
            code="invalid_initial_stage",
            message="新建商机的阶段固定为「报价」，请建好后再推进",
        )
    spec = payload.spec or _spec_from_model(model)
    amount = round(float(payload.amount), 2)

    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO deals (customer_id, product_type, model, spec, amount, deposit, balance,"
            " stage, closed_at, created_at, updated_at, drive_type, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'quote', NULL, ?, ?, ?, ?)",
            (
                payload.customer_id,
                product_type,
                model,
                spec,
                amount,
                round(float(payload.deposit or 0), 2),
                round(float(payload.balance or 0), 2),
                now_iso(),
                now_iso(),
                drive,
                payload.note,
            ),
        )
        deal_id = int(cur.lastrowid or 0)
        add_entry(
            conn,
            object_type="deal",
            object_id=deal_id,
            kind="create",
            customer_id=payload.customer_id,
            deal_id=deal_id,
            content=(
                f"创建商机：{product_type or '未填产品'} {model or ''} {spec or ''}，"
                f"报价 ¥{amount:,.2f}"
            ).strip(),
            detail={"amount": amount, "drive_type": drive},
        )
        row = _deal_row(conn, deal_id)
    return _out(row)


@router.put("/deals/{deal_id}", response_model=DealOut)
def update_deal(deal_id: int, payload: DealUpdate) -> DealOut:
    fields = payload.model_dump(exclude_unset=True)
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE}

    with db_conn() as conn:
        old = _deal_row(conn, deal_id)

        # ① 先判冻结：锁定/流失的商机，除备注外一律拦掉（错误码优先于字段校验）
        if old["order_id"] is not None:
            if [k for k in updates if k not in _LOCKED_ALLOWED]:
                raise _deal_locked()
        elif old["stage"] == "lost":
            if [k for k in updates if k not in _LOCKED_ALLOWED]:
                raise ApiError(
                    status_code=409,
                    code="deal_frozen",
                    message="该商机已判流失，不可修改（只允许改备注）",
                )

        # ② 再校验取值
        if "stage" in updates and updates["stage"] is None:
            raise ApiError(status_code=400, code="stage_required", message="阶段不能为空")
        if updates.get("stage") == "lost":
            raise ApiError(
                status_code=400,
                code="stage_via_action",
                message="判流失请用「判流失」操作并填写流失原因",
            )
        if updates.get("stage") is not None:
            value = str(updates["stage"]).strip()
            if value not in STAGES:
                raise _invalid_stage(value)
            updates["stage"] = value
        if "drive_type" in updates:
            updates["drive_type"] = _drive_type(updates["drive_type"])
        if "product_type" in updates:
            updates["product_type"] = _product_type(updates["product_type"])
        if "model" in updates:
            updates["model"] = _model(updates["model"])
        if "amount" in updates and updates["amount"] is None:
            raise ApiError(status_code=400, code="amount_required", message="金额不能为空")
        for key in ("amount", "deposit", "balance"):
            if updates.get(key) is not None:
                updates[key] = round(float(updates[key]), 2)

        if not updates:
            return _out(old)

        old_stage = old["stage"]
        new_stage = updates.get("stage", old_stage)
        if new_stage != old_stage:
            if new_stage == "won":
                updates["closed_at"] = now_local_iso()
            elif old_stage == "won":
                updates["closed_at"] = None

        # ③ 字段真变化 → 一条「编辑」履历
        lines, detail = change_summary(dict(old), updates, _CHANGE_TRACKED)
        if lines:
            add_entry(
                conn,
                object_type="deal",
                object_id=deal_id,
                kind="change",
                customer_id=old["customer_id"],
                deal_id=deal_id,
                content="；".join(lines),
                detail=detail,
            )

        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE deals SET {assignments}, updated_at = ? WHERE id = ?",
            [*updates.values(), now_iso(), deal_id],
        )

        # ④ 阶段变化 → 一条「状态变更」履历
        if new_stage != old_stage:
            add_entry(
                conn,
                object_type="deal",
                object_id=deal_id,
                kind="stage",
                customer_id=old["customer_id"],
                deal_id=deal_id,
                content=(
                    f"阶段推进：{DEAL_STAGE_LABELS.get(old_stage, old_stage)}"
                    f" → {DEAL_STAGE_LABELS.get(new_stage, new_stage)}"
                ),
                detail={"stage": {"from": old_stage, "to": new_stage}},
            )

        row = _deal_row(conn, deal_id)
    return _out(row)


# ---------------- 生成订单 ----------------


def _create_order(conn, deal_id: int, payload: dict, *, require_receiver: bool = True) -> tuple[dict, dict]:
    """生成订单的唯一实现；`/win` 兼容端点也走这里。"""
    deal = _deal_row(conn, deal_id)

    if conn.execute("SELECT 1 FROM orders WHERE deal_id = ?", (deal_id,)).fetchone():
        raise ApiError(status_code=409, code="order_exists", message="该商机已有订单")
    if deal["stage"] != "won":
        raise ApiError(
            status_code=409, code="deal_not_won", message="先把阶段推进到「成交」，再生成订单"
        )

    amount = round(float(payload.get("amount") or deal["amount"] or 0), 2)
    if amount <= 0:
        raise ApiError(status_code=400, code="invalid_amount", message="订单金额必须大于 0")

    raw_deposit = payload.get("deposit")
    if raw_deposit is None:
        raise ApiError(status_code=400, code="deposit_required", message="请填写押金金额")
    deposit = round(float(raw_deposit), 2)
    if deposit < 0 or deposit > amount:
        raise ApiError(
            status_code=400,
            code="invalid_deposit",
            message=f"押金必须在 0 到订单金额（¥{amount:,.2f}）之间",
        )
    # Q-D：尾款服务端强制算，不采信前端
    balance = round(amount - deposit, 2)

    mode = str(payload.get("logistics_mode") or "").strip()
    if mode not in LOGISTICS_MODE_LABELS:
        raise ApiError(
            status_code=400,
            code="invalid_logistics_mode",
            message="物流方式只能是 free（包邮）/ agent（代办）/ self（自提）",
        )
    carrier_id = payload.get("carrier_id")
    if mode in ("free", "agent"):
        if not carrier_id:
            raise ApiError(
                status_code=400, code="carrier_required", message="包邮 / 代办 必须选择物流公司"
            )
        if conn.execute(
            "SELECT 1 FROM carriers WHERE id = ?", (int(carrier_id),)
        ).fetchone() is None:
            raise ApiError(status_code=400, code="carrier_not_found", message="物流公司不存在")
    else:
        carrier_id = None

    fee = round(float(payload.get("logistics_fee") or 0), 2) if mode != "self" else 0.0
    if fee < 0:
        raise ApiError(status_code=400, code="invalid_logistics_fee", message="物流费用不能为负")

    # 收货：优先地址簿；手填的回存地址簿（复购可直接选）
    address_id = payload.get("address_id")
    receiver_name = (payload.get("receiver_name") or "").strip()
    receiver_phone = (payload.get("receiver_phone") or "").strip()
    receiver_address = (payload.get("receiver_address") or "").strip()

    if address_id:
        addr = conn.execute(
            "SELECT * FROM customer_addresses WHERE id = ? AND customer_id = ?",
            (int(address_id), deal["customer_id"]),
        ).fetchone()
        if addr is None:
            raise ApiError(
                status_code=400, code="address_not_found", message="该客户没有这条收货地址"
            )
        receiver_name, receiver_phone, receiver_address = (
            addr["receiver_name"],
            addr["phone"],
            addr["address"],
        )
    elif not (receiver_name and receiver_phone and receiver_address):
        # 自提不需要收货信息（现场取货），其它方式必须填全
        if require_receiver and mode != "self":
            raise ApiError(
                status_code=400,
                code="receiver_required",
                message="请选择历史地址，或填全收货人 / 电话 / 地址",
            )
        receiver_name = receiver_phone = receiver_address = None
    else:
        cur = conn.execute(
            "INSERT INTO customer_addresses (customer_id, label, receiver_name, phone, address,"
            " is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (
                deal["customer_id"],
                payload.get("address_label") or None,
                receiver_name,
                receiver_phone,
                receiver_address,
                now_iso(),
                now_iso(),
            ),
        )
        address_id = int(cur.lastrowid or 0)

    order_no = next_no(conn, "orders", "order_no", "SO", now_local_iso()[:8])
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO orders (order_no, customer_id, deal_id, product_type, model, spec, amount,"
        " deposit_amount, balance_amount, deposit_paid, balance_paid, logistics_mode, carrier_id,"
        " logistics_fee, tracking_no, address_id, receiver_name, receiver_phone, receiver_address,"
        " status, note, owner, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?,"
        " 'pending_payment', ?, ?, ?, ?)",
        (
            order_no,
            deal["customer_id"],
            deal_id,
            deal["product_type"],
            deal["model"],
            deal["spec"],
            amount,
            deposit,
            balance,
            mode,
            carrier_id,
            fee,
            payload.get("tracking_number") or None,
            address_id,
            receiver_name,
            receiver_phone,
            receiver_address,
            payload.get("note") or None,
            deal["owner"],
            now,
            now,
        ),
    )
    order_id = int(cur.lastrowid or 0)

    conn.execute(
        "UPDATE deals SET stage = 'won', closed_at = COALESCE(closed_at, ?), order_id = ?,"
        " locked_at = ?, updated_at = ? WHERE id = ?",
        (now_local_iso(), order_id, now_local_iso(), now, deal_id),
    )

    carrier_name = None
    if carrier_id:
        carrier_row = conn.execute(
            "SELECT name FROM carriers WHERE id = ?", (carrier_id,)
        ).fetchone()
        carrier_name = carrier_row["name"] if carrier_row else None
    logistics_text = LOGISTICS_MODE_LABELS[mode] + (f"/{carrier_name}" if carrier_name else "")

    add_entry(
        conn,
        object_type="deal",
        object_id=deal_id,
        kind="order",
        customer_id=deal["customer_id"],
        deal_id=deal_id,
        content=(
            f"生成订单 {order_no}，押金 ¥{deposit:,.2f}，尾款 ¥{balance:,.2f}，物流 {logistics_text}"
        ),
        detail={"order_id": order_id, "order_no": order_no, "deposit": deposit, "balance": balance},
    )
    conn.execute(
        "INSERT INTO order_status_log (order_id, from_status, to_status, event_type, note, detail,"
        " created_at) VALUES (?, NULL, 'pending_payment', 'order', ?, ?, ?)",
        (
            order_id,
            f"生成订单 {order_no}：总额 ¥{amount:,.2f}，押金 ¥{deposit:,.2f}，尾款 ¥{balance:,.2f}",
            '{"order_no": "%s"}' % order_no,
            now,
        ),
    )

    deal_row = _deal_row(conn, deal_id)
    order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(deal_row), dict(order_row)


@router.post("/deals/{deal_id}/orders", response_model=dict)
def create_order(deal_id: int, payload: dict) -> dict:
    """生成订单（只有「成交」阶段可生成；生成后商机锁定）。"""
    with db_conn() as conn:
        deal_row, order_row = _create_order(conn, deal_id, payload)
        timeline = entries_for(
            conn, object_type="deal", object_id=deal_id, include_order_events=True
        )
        data = dict(deal_row)
        data.pop("customer_name", None)
        data["locked"] = True
        return {
            "deal": DealOut(**data).model_dump(),
            "order": order_row,
            "timeline": timeline,
        }


@router.post("/deals/{deal_id}/win", response_model=dict)
def win_deal(deal_id: int) -> dict:
    """兼容旧前端：无参成交并生成订单（押金=全额、自提、运费 0）。

    定稿后的正路是 ``POST /deals/{id}/orders``（带押金 / 物流 / 收货信息）。
    """
    with db_conn() as conn:
        deal = _deal_row(conn, deal_id)
        if deal["stage"] != "won":
            if deal["order_id"] is not None:
                raise _deal_locked()
            conn.execute(
                "UPDATE deals SET stage = 'won', closed_at = ?, updated_at = ? WHERE id = ?",
                (now_local_iso(), now_iso(), deal_id),
            )
            add_entry(
                conn,
                object_type="deal",
                object_id=deal_id,
                kind="stage",
                customer_id=deal["customer_id"],
                deal_id=deal_id,
                content=f"阶段推进：{DEAL_STAGE_LABELS.get(deal['stage'], deal['stage'])} → 成交",
                detail={"stage": {"from": deal["stage"], "to": "won"}},
            )
            deal = _deal_row(conn, deal_id)
        payload = {
            "amount": deal["amount"],
            "deposit": deal["amount"],
            "logistics_mode": "self",
            "logistics_fee": 0,
        }
        deal_row, order_row = _create_order(conn, deal_id, payload, require_receiver=False)
        data = dict(deal_row)
        data.pop("customer_name", None)
        data["locked"] = True
        return {"deal": DealOut(**data).model_dump(), "order": order_row}


@router.post("/deals/{deal_id}/lose", response_model=DealOut)
def lose_deal(deal_id: int, payload: dict) -> DealOut:
    """判流失（必须给原因）。"""
    reason = (payload.get("lost_reason") or "").strip()
    other = (payload.get("lost_reason_other") or "").strip()
    valid = DEAL_LOST_REASON.__args__  # type: ignore[attr-defined]
    if not reason:
        raise ApiError(status_code=400, code="lost_reason_required", message="流失原因不能为空")
    if reason not in valid:
        raise ApiError(status_code=400, code="invalid_lost_reason", message="无效的流失原因")
    if reason == "other" and not other:
        raise ApiError(
            status_code=400, code="lost_reason_other_required", message="选「其他」时请填写说明"
        )

    with db_conn() as conn:
        old = _deal_row(conn, deal_id)
        if old["order_id"] is not None:
            raise _deal_locked()
        if old["stage"] == "lost":
            raise ApiError(status_code=409, code="already_lost", message="该商机已判流失")

        conn.execute(
            "UPDATE deals SET stage = 'lost', lost_reason = ?, lost_reason_other = ?,"
            " closed_at = NULL, updated_at = ? WHERE id = ?",
            (reason, other or None, now_iso(), deal_id),
        )
        add_entry(
            conn,
            object_type="deal",
            object_id=deal_id,
            kind="stage",
            customer_id=old["customer_id"],
            deal_id=deal_id,
            content=(
                f"阶段推进：{DEAL_STAGE_LABELS.get(old['stage'], old['stage'])}"
                f" → 流失（{other or reason}）"
            ),
            detail={"stage": {"from": old["stage"], "to": "lost"}, "lost_reason": reason},
        )
        row = _deal_row(conn, deal_id)
    return _out(row)
