"""商机 endpoints（PLANNER-V3 §5.5 / §6.2）。

职责边界：
- 这里只做「取参 + 校验 + 错误映射 + 事务编排」；
- 订单号生成走 ``app.services.next_no``，履历写入走 ``app.timeline.add_entry``；
- 金额一律 ``round(x, 2)``；订单总额只取商机报价，定金 + 尾款 = 报价金额。
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from app import dicts as dict_svc
from app.deal_tags import (
    add_manual_tag,
    delete_manual_tag,
    ensure_deal_tags_editable,
    list_deal_tags,
    sync_pending_quote_tags,
)
from app.db import db_conn
from app.enums import (
    DEAL_LOST_REASON,
    DEAL_STAGE_LABELS,
    DEAL_STAGE_ORDER,
    DRIVE_TYPE_LABELS,
    LOGISTICS_MODE_LABELS,
)
from app.errors import ApiError
from app.models import (
    DealDetailOut,
    DealIn,
    DealItemIn,
    DealItemOut,
    DealItemUpdate,
    DealOut,
    DealTagIn,
    DealTagOut,
    DealUpdate,
    normalize_spec,
)
from app.product_catalog import config_summary, get_product, product_snapshot
from app.routers.auth import require_auth
from app.security import now_iso, now_local_iso
from app.services import next_no, resolve_carrier_contact, upgrade_intent
from app.timeline import add_entry, change_summary, entries_for

router = APIRouter(
    prefix="/api/crm",
    tags=["deals"],
    dependencies=[Depends(require_auth)],
)

STAGES = DEAL_STAGE_ORDER
#: 会写「编辑」履历的字段
_CHANGE_TRACKED = (
    "product_id", "product_code_snapshot", "product_name_snapshot",
    "product_config_snapshot", "product_type", "model", "spec", "drive_type",
    "amount", "note",
)
_UPDATABLE = _CHANGE_TRACKED + ("stage",)
#: 流失商机只允许补备注；已生成订单的商机完全只读
_FROZEN_ALLOWED = ("note",)


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
        message="该商机已生成订单并归档，仅可查看",
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
            return normalize_spec((item.get("meta") or {}).get("size"))
    return None


def _product(conn, product_id: int) -> dict:
    product = get_product(conn, int(product_id), active_only=True)
    if product is None:
        raise ApiError(status_code=400, code="product_not_found", message="关联产品不存在或已停用")
    return product


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


def _deal_items(conn, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_items WHERE deal_id = ? AND is_delete = 0"
        " ORDER BY sort, id",
        (deal_id,),
    ).fetchall()


def _sync_deal_summary(conn, deal_id: int, *, touch: bool = True) -> None:
    """用产品明细同步商机列表所展示的首项摘要与合计金额。"""
    items = _deal_items(conn, deal_id)
    if not items:
        raise ApiError(
            status_code=409,
            code="deal_item_required",
            message="商机至少保留一条产品明细",
        )
    first = items[0]
    total = round(sum(float(row["amount"] or 0) for row in items), 2)
    conn.execute(
        "UPDATE deals SET product_id = ?, product_code_snapshot = ?,"
        " product_name_snapshot = ?, product_config_snapshot = ?,"
        " product_type = ?, model = ?, drive_type = ?, spec = ?, amount = ?,"
        " updated_at = ? WHERE id = ?",
        (
            first["product_id"],
            first["product_code_snapshot"],
            first["product_name_snapshot"],
            first["product_config_snapshot"],
            first["product_type"],
            first["model"],
            first["drive_type"],
            first["spec"],
            total,
            now_iso() if touch else first["updated_at"],
            deal_id,
        ),
    )


def _ensure_deal_editable(old) -> None:
    if old["order_id"] is not None:
        raise _deal_locked()
    if old["stage"] == "lost":
        raise ApiError(
            status_code=409,
            code="deal_frozen",
            message="该商机已判流失，不能修改产品明细",
        )


def _item_values(conn, payload: DealItemIn | DealItemUpdate, old=None) -> dict:
    product_id = payload.product_id if getattr(payload, "product_id", None) is not None else (
        old["product_id"] if old is not None else None
    )
    if not product_id:
        raise ApiError(
            status_code=400,
            code="product_required",
            message="产品明细必须选择产品",
        )
    product = _product(conn, int(product_id))
    snapshot = product_snapshot(product)
    requested_drive = (
        product.get("drive_type")
        or (getattr(payload, "drive_type", None) if getattr(payload, "drive_type", None) is not None else None)
        or (old["drive_type"] if old is not None else None)
    )
    drive = _drive_type(requested_drive) if requested_drive else None
    quantity = (
        payload.quantity
        if getattr(payload, "quantity", None) is not None
        else (old["quantity"] if old is not None else 1)
    )
    unit_price = (
        payload.unit_price
        if getattr(payload, "unit_price", None) is not None
        else (old["unit_price"] if old is not None else 0)
    )
    spec = (
        payload.spec
        if "spec" in getattr(payload, "model_fields_set", set())
        else (old["spec"] if old is not None else None)
    )
    production_spec = (
        payload.production_spec
        if "production_spec" in getattr(payload, "model_fields_set", set())
        else (old["production_spec"] if old is not None else None)
    )
    note = (
        payload.note
        if "note" in getattr(payload, "model_fields_set", set())
        else (old["note"] if old is not None else None)
    )
    return {
        **snapshot,
        "product_type": product.get("category"),
        "model": product.get("code"),
        "drive_type": drive,
        "quantity": int(quantity),
        "spec": spec,
        "production_spec": production_spec,
        "unit_price": round(float(unit_price), 2),
        "amount": round(float(unit_price) * int(quantity), 2),
        "note": note,
    }


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
        where.append(
            "(d.model LIKE ? OR d.spec LIKE ? OR c.name LIKE ?"
            " OR d.product_name_snapshot LIKE ? OR d.product_code_snapshot LIKE ?)"
        )
        params.extend([like, like, like, like, like])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT d.*, c.name AS customer_name,"
            " (SELECT COUNT(*) FROM deal_quotes q"
            "  WHERE q.deal_id = d.id AND q.is_delete = 0) AS quote_count,"
            " (SELECT q.quote_no FROM deal_quotes q"
            "  WHERE q.deal_id = d.id AND q.status = 'confirmed' AND q.is_delete = 0"
            "  ORDER BY q.id DESC LIMIT 1) AS confirmed_quote_no"
            " FROM deals d"
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
        data["items"] = [dict(item) for item in _deal_items(conn, deal_id)]
        data["tags"] = list_deal_tags(conn, deal_id)
    return DealDetailOut(**data)


@router.get("/deals/{deal_id}/tags", response_model=list[DealTagOut])
def get_deal_tags(deal_id: int) -> list[DealTagOut]:
    with db_conn() as conn:
        _deal_row(conn, deal_id)
        return [DealTagOut(**row) for row in list_deal_tags(conn, deal_id)]


@router.post("/deals/{deal_id}/tags", response_model=list[DealTagOut])
def create_deal_tag(deal_id: int, payload: DealTagIn) -> list[DealTagOut]:
    with db_conn() as conn:
        _deal_row(conn, deal_id)
        ensure_deal_tags_editable(conn, deal_id)
        return [
            DealTagOut(**row)
            for row in add_manual_tag(conn, deal_id, payload.name)
        ]


@router.delete("/deals/{deal_id}/tags/{tag_link_id}", response_model=list[DealTagOut])
def remove_deal_tag(deal_id: int, tag_link_id: int) -> list[DealTagOut]:
    with db_conn() as conn:
        _deal_row(conn, deal_id)
        ensure_deal_tags_editable(conn, deal_id)
        return [
            DealTagOut(**row)
            for row in delete_manual_tag(conn, deal_id, tag_link_id)
        ]


# ---------------- 新建 / 修改 ----------------


@router.post("/deals", response_model=DealOut)
def create_deal(payload: DealIn) -> DealOut:
    with db_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND is_delete = 0",
            (payload.customer_id,),
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="客户不存在")
        product = _product(conn, payload.product_id) if payload.product_id else None

    # 新流程：商机本身只保存客户与备注，产品配置进入报价单。
    # 仍接受产品字段，用于兼容旧页面和旧数据。
    legacy_config = bool(
        payload.product_id
        or payload.product_type
        or payload.model
        or payload.spec
        or payload.amount > 0
        or payload.drive_type
    )
    if legacy_config:
        linked_drive = product.get("drive_type") if product else None
        drive = _drive_type(linked_drive or payload.drive_type)
        if product:
            product_type = product["category"]
            model = product["code"]
            snapshot = product_snapshot(product)
        else:
            product_type = _product_type(payload.product_type)
            model = _model(payload.model)
            snapshot = {
                "product_id": None,
                "product_code_snapshot": None,
                "product_name_snapshot": None,
                "product_config_snapshot": None,
            }
    else:
        drive = None
        product_type = None
        model = None
        snapshot = {
            "product_id": None,
            "product_code_snapshot": None,
            "product_name_snapshot": None,
            "product_config_snapshot": None,
        }
    # 定稿：新建阶段固定「报价」
    if payload.stage and payload.stage.strip() not in ("quote", ""):
        raise ApiError(
            status_code=400,
            code="invalid_initial_stage",
            message="新建商机的阶段固定为「报价」，请建好后再推进",
        )
    spec = payload.spec or (None if product else _spec_from_model(model))
    amount = round(float(payload.amount), 2)

    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO deals (customer_id, product_id, product_code_snapshot,"
            " product_name_snapshot, product_config_snapshot, product_type, model, spec,"
            " amount, deposit, balance, stage, closed_at, created_at, updated_at, drive_type, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'quote', NULL, ?, ?, ?, ?)",
            (
                payload.customer_id,
                snapshot["product_id"],
                snapshot["product_code_snapshot"],
                snapshot["product_name_snapshot"],
                snapshot["product_config_snapshot"],
                product_type,
                model,
                spec,
                amount,
                0,
                0,
                now_iso(),
                now_iso(),
                drive,
                payload.note,
            ),
        )
        deal_id = int(cur.lastrowid or 0)
        if legacy_config:
            now = now_iso()
            conn.execute(
                "INSERT INTO deal_items (deal_id, product_id, product_code_snapshot,"
                " product_name_snapshot, product_config_snapshot, product_type, model,"
                " drive_type, quantity, spec, production_spec, unit_price, amount, note,"
                " sort, created_at, updated_at, create_time, update_time, is_delete)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, ?, ?, ?, 0, ?, ?, '', '', 0)",
                (
                    deal_id,
                    snapshot["product_id"],
                    snapshot["product_code_snapshot"],
                    snapshot["product_name_snapshot"],
                    snapshot["product_config_snapshot"],
                    product_type,
                    model,
                    drive,
                    spec,
                    amount,
                    amount,
                    payload.note,
                    now,
                    now,
                ),
            )
        add_entry(
            conn,
            object_type="deal",
            object_id=deal_id,
            kind="create",
            customer_id=payload.customer_id,
            deal_id=deal_id,
            content=(
                f"创建商机：{snapshot['product_name_snapshot'] or product_type or '待创建报价单'}"
                f" {model or ''} {spec or ''}"
                + (f"，报价 ¥{amount:,.2f}" if amount > 0 else "")
            ).strip(),
            detail={"amount": amount, "drive_type": drive},
        )
        # 意向升级：客户绑定商机 → 至少「中」
        upgrade_intent(conn, "customer", payload.customer_id, "medium")
        row = _deal_row(conn, deal_id)
    return _out(row)


@router.post("/deals/{deal_id}/items", response_model=DealItemOut)
def add_deal_item(deal_id: int, payload: DealItemIn) -> DealItemOut:
    with db_conn() as conn:
        old = _deal_row(conn, deal_id)
        _ensure_deal_editable(old)
        values = _item_values(conn, payload)
        sort_row = conn.execute(
            "SELECT COALESCE(MAX(sort), -1) + 1 AS next_sort FROM deal_items"
            " WHERE deal_id = ? AND is_delete = 0",
            (deal_id,),
        ).fetchone()
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO deal_items (deal_id, product_id, product_code_snapshot,"
            " product_name_snapshot, product_config_snapshot, product_type, model,"
            " drive_type, quantity, spec, production_spec, unit_price, amount, note,"
            " sort, created_at, updated_at, create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 0)",
            (
                deal_id,
                values["product_id"],
                values["product_code_snapshot"],
                values["product_name_snapshot"],
                values["product_config_snapshot"],
                values["product_type"],
                values["model"],
                values["drive_type"],
                values["quantity"],
                values["spec"],
                values["production_spec"],
                values["unit_price"],
                values["amount"],
                values["note"],
                int(sort_row["next_sort"]),
                now,
                now,
            ),
        )
        item_id = int(cur.lastrowid or 0)
        _sync_deal_summary(conn, deal_id)
        row = conn.execute(
            "SELECT * FROM deal_items WHERE id = ? AND is_delete = 0", (item_id,)
        ).fetchone()
    return DealItemOut(**dict(row))


@router.put("/deals/{deal_id}/items/{item_id}", response_model=DealItemOut)
def update_deal_item(
    deal_id: int, item_id: int, payload: DealItemUpdate
) -> DealItemOut:
    with db_conn() as conn:
        deal = _deal_row(conn, deal_id)
        _ensure_deal_editable(deal)
        old = conn.execute(
            "SELECT * FROM deal_items WHERE id = ? AND deal_id = ? AND is_delete = 0",
            (item_id, deal_id),
        ).fetchone()
        if old is None:
            raise HTTPException(status_code=404, detail="产品明细不存在")
        values = _item_values(conn, payload, old)
        conn.execute(
            "UPDATE deal_items SET product_id = ?, product_code_snapshot = ?,"
            " product_name_snapshot = ?, product_config_snapshot = ?, product_type = ?,"
            " model = ?, drive_type = ?, quantity = ?, spec = ?, production_spec = ?,"
            " unit_price = ?, amount = ?, note = ?, updated_at = ? WHERE id = ?",
            (
                values["product_id"],
                values["product_code_snapshot"],
                values["product_name_snapshot"],
                values["product_config_snapshot"],
                values["product_type"],
                values["model"],
                values["drive_type"],
                values["quantity"],
                values["spec"],
                values["production_spec"],
                values["unit_price"],
                values["amount"],
                values["note"],
                now_iso(),
                item_id,
            ),
        )
        _sync_deal_summary(conn, deal_id)
        row = conn.execute("SELECT * FROM deal_items WHERE id = ?", (item_id,)).fetchone()
    return DealItemOut(**dict(row))


@router.delete("/deals/{deal_id}/items/{item_id}")
def delete_deal_item(deal_id: int, item_id: int) -> dict:
    with db_conn() as conn:
        deal = _deal_row(conn, deal_id)
        _ensure_deal_editable(deal)
        items = _deal_items(conn, deal_id)
        if not any(int(row["id"]) == item_id for row in items):
            raise HTTPException(status_code=404, detail="产品明细不存在")
        if len(items) <= 1:
            raise ApiError(
                status_code=409,
                code="last_deal_item",
                message="商机至少保留一条产品明细，不能全部删除",
            )
        conn.execute(
            "UPDATE deal_items SET is_delete = 1, updated_at = ? WHERE id = ?",
            (now_iso(), item_id),
        )
        _sync_deal_summary(conn, deal_id)
    return {"ok": True}


@router.put("/deals/{deal_id}", response_model=DealOut)
def update_deal(deal_id: int, payload: DealUpdate) -> DealOut:
    fields = payload.model_dump(exclude_unset=True)
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE}

    with db_conn() as conn:
        old = _deal_row(conn, deal_id)

        # ① 先判冻结：锁定/流失的商机，除备注外一律拦掉（错误码优先于字段校验）
        requested_fields = set(updates)
        if "product_id" in fields:
            requested_fields.add("product_id")
        if old["order_id"] is not None:
            if requested_fields:
                raise _deal_locked()
        elif old["stage"] == "lost":
            if [k for k in requested_fields if k not in _FROZEN_ALLOWED]:
                raise ApiError(
                    status_code=409,
                    code="deal_frozen",
                    message="该商机已判流失，不可修改（只允许改备注）",
                )

        # ② 关联产品：只保存主档外键与快照；主档后续改名不改写已建商机。
        linked_product_id = old["product_id"]
        if "product_id" in fields:
            requested_product_id = fields["product_id"]
            if requested_product_id is None:
                updates.update({
                    "product_id": None,
                    "product_code_snapshot": None,
                    "product_name_snapshot": None,
                    "product_config_snapshot": None,
                })
                linked_product_id = None
            else:
                product = _product(conn, int(requested_product_id))
                snapshot = product_snapshot(product)
                updates.update({
                    "product_id": snapshot["product_id"],
                    "product_code_snapshot": snapshot["product_code_snapshot"],
                    "product_name_snapshot": snapshot["product_name_snapshot"],
                    "product_config_snapshot": snapshot["product_config_snapshot"],
                    "product_type": snapshot["product_type"],
                    "model": snapshot["model"],
                })
                if snapshot.get("drive_type"):
                    updates["drive_type"] = snapshot["drive_type"]
                elif "drive_type" not in updates:
                    updates["drive_type"] = None
                linked_product_id = snapshot["product_id"]

        if linked_product_id:
            linked_product = conn.execute(
                "SELECT drive_type FROM products WHERE id = ? AND is_delete = 0",
                (linked_product_id,),
            ).fetchone()
            if linked_product and linked_product["drive_type"]:
                updates["drive_type"] = linked_product["drive_type"]

        # ③ 再校验取值
        if "stage" in updates and updates["stage"] is None:
            raise ApiError(status_code=400, code="stage_required", message="阶段不能为空")
        if updates.get("stage") == "lost":
            raise ApiError(
                status_code=400,
                code="stage_via_action",
                message="判流失请用「判流失」操作并填写流失原因",
            )
        if updates.get("stage") == "won":
            raise ApiError(
                status_code=400,
                code="stage_via_customer_confirmation",
                message="生成订单并记录客户确认后，商机才会进入「成交」",
            )
        if updates.get("stage") is not None:
            value = str(updates["stage"]).strip()
            if value not in STAGES:
                raise _invalid_stage(value)
            updates["stage"] = value
        if "drive_type" in updates:
            updates["drive_type"] = _drive_type(updates["drive_type"])
        if "product_type" in updates:
            if linked_product_id:
                updates["product_type"] = str(updates["product_type"] or "").strip() or None
            else:
                updates["product_type"] = _product_type(updates["product_type"])
        if "model" in updates:
            if linked_product_id:
                updates["model"] = str(updates["model"] or "").strip() or None
            else:
                updates["model"] = _model(updates["model"])
        if "amount" in updates and updates["amount"] is None:
            raise ApiError(status_code=400, code="amount_required", message="金额不能为空")
        for key in ("amount",):
            if updates.get(key) is not None:
                updates[key] = round(float(updates[key]), 2)

        # 兼容旧页面：单产品商机仍可通过商机编辑改产品/金额；多产品必须走明细接口。
        legacy_fields = {
            key for key in (
                "product_id", "product_type", "model", "spec", "drive_type", "amount"
            ) if key in updates
        }
        if legacy_fields and any(key in fields for key in legacy_fields):
            items = _deal_items(conn, deal_id)
            if len(items) > 1:
                raise ApiError(
                    status_code=400,
                    code="use_deal_item_api",
                    message="多产品商机请在产品明细中修改，不能直接覆盖商机总额",
                )
            if items:
                first = items[0]
                conn.execute(
                    "UPDATE deal_items SET product_id = ?, product_code_snapshot = ?,"
                    " product_name_snapshot = ?, product_config_snapshot = ?,"
                    " product_type = ?, model = ?, drive_type = ?, spec = ?,"
                    " unit_price = ?, amount = ?, updated_at = ? WHERE id = ?",
                    (
                        updates.get("product_id", first["product_id"]),
                        updates.get("product_code_snapshot", first["product_code_snapshot"]),
                        updates.get("product_name_snapshot", first["product_name_snapshot"]),
                        updates.get("product_config_snapshot", first["product_config_snapshot"]),
                        updates.get("product_type", first["product_type"]),
                        updates.get("model", first["model"]),
                        updates.get("drive_type", first["drive_type"]),
                        updates.get("spec", first["spec"]),
                        updates.get("amount", first["unit_price"]),
                        updates.get("amount", first["amount"]),
                        now_iso(),
                        first["id"],
                    ),
                )

        if not updates:
            return _out(old)

        old_stage = old["stage"]
        new_stage = updates.get("stage", old_stage)
        if new_stage != old_stage:
            if new_stage == "won":
                updates["closed_at"] = now_local_iso()
            elif old_stage == "won":
                updates["closed_at"] = None

        # ④ 字段真变化 → 一条「编辑」履历
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

        # ⑤ 阶段变化 → 一条「状态变更」履历
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


def _create_order(
    conn,
    deal_id: int,
    payload: dict,
    *,
    require_receiver: bool = True,
    quote_id: int | None = None,
) -> tuple[dict, dict]:
    """生成订单的唯一实现；`/win` 兼容端点也走这里。"""
    deal = _deal_row(conn, deal_id)
    quote = None
    if quote_id is not None:
        quote = conn.execute(
            "SELECT * FROM deal_quotes WHERE id = ? AND deal_id = ? AND is_delete = 0",
            (quote_id, deal_id),
        ).fetchone()
        if quote is None:
            raise HTTPException(status_code=404, detail="报价单不存在")
        if quote["status"] != "confirmed":
            raise ApiError(
                status_code=409,
                code="quote_not_confirmed",
                message="客户确认报价单后才能生成订单",
            )
        items = conn.execute(
            "SELECT * FROM quote_items WHERE quote_id = ? AND is_delete = 0"
            " ORDER BY sort, id",
            (quote_id,),
        ).fetchall()
    else:
        items = _deal_items(conn, deal_id)

    existing_sql = (
        "SELECT 1 FROM orders WHERE quote_id = ? AND is_delete = 0"
        if quote_id is not None
        else "SELECT 1 FROM orders WHERE deal_id = ? AND is_delete = 0"
    )
    if conn.execute(existing_sql, (quote_id if quote_id is not None else deal_id,)).fetchone():
        raise ApiError(status_code=409, code="order_exists", message="该商机已有订单")
    if not items:
        raise ApiError(
            status_code=409,
            code="deal_item_required",
            message="商机没有产品明细，不能生成订单",
        )
    if quote_id is None and deal["stage"] not in ("confirm", "won"):
        raise ApiError(
            status_code=409,
            code="deal_not_ready",
            message="先把阶段推进到「待客户确认」，再生成订单",
        )

    # 商品金额取明细合计；优惠是整单数据，运费独立记录。
    product_total = round(sum(float(row["amount"] or 0) for row in items), 2)
    if product_total <= 0:
        raise ApiError(status_code=400, code="invalid_amount", message="产品明细合计必须大于 0")
    discount = round(float(payload.get("discount_amount") or 0), 2)
    if discount < 0 or discount > product_total:
        raise ApiError(
            status_code=400,
            code="invalid_discount",
            message=f"优惠必须在 0 到产品合计（¥{product_total:,.2f}）之间",
        )
    product_payable = round(product_total - discount, 2)

    raw_deposit = payload.get("deposit")
    if raw_deposit is None:
        raise ApiError(status_code=400, code="deposit_required", message="请填写定金金额")
    deposit = round(float(raw_deposit), 2)
    if deposit < 0:
        raise ApiError(
            status_code=400,
            code="invalid_deposit",
            message="定金不能为负",
        )

    mode = str(payload.get("logistics_mode") or "").strip()
    if mode not in LOGISTICS_MODE_LABELS:
        raise ApiError(
            status_code=400,
            code="invalid_logistics_mode",
            message="物流方式只能是 free（包邮）/ agent（代办）/ self（自提）",
        )
    carrier_id = payload.get("carrier_id")
    carrier_contact = None
    if mode in ("free", "agent"):
        if not carrier_id:
            raise ApiError(
                status_code=400, code="carrier_required", message="包邮 / 代办 必须选择物流公司"
            )
        carrier_contact = resolve_carrier_contact(
            conn, carrier_id, payload.get("carrier_contact_id")
        )
    else:
        carrier_id = None

    fee = round(float(payload.get("logistics_fee") or 0), 2) if mode != "self" else 0.0
    if fee < 0:
        raise ApiError(status_code=400, code="invalid_logistics_fee", message="物流费用不能为负")
    amount = round(product_payable + fee, 2)
    if deposit > amount:
        raise ApiError(
            status_code=400,
            code="invalid_deposit",
            message=f"定金不能超过订单应收（¥{amount:,.2f}）",
        )
    # Q-D：尾款服务端强制算，不采信前端
    balance = round(amount - deposit, 2)

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
    order_status = "pending_payment" if quote_id is not None else "pending_confirmation"
    summary_item = items[0]
    order_name = (
        (quote["title"] if quote is not None else deal["title"])
        or summary_item["product_name_snapshot"]
        or summary_item["product_code_snapshot"]
        or "订单"
    )
    cur = conn.execute(
        "INSERT INTO orders (order_no, order_name, customer_id, deal_id, quote_id, product_id,"
        " product_code_snapshot, product_name_snapshot, product_config_snapshot,"
        " product_type, model, spec, amount, product_total, discount_amount,"
        " discount_reason, product_payable,"
        " deposit_amount, balance_amount, deposit_paid, balance_paid, logistics_mode, carrier_id,"
        " carrier_contact_id, carrier_contact_name, carrier_contact_phone,"
        " logistics_fee, tracking_no, address_id, receiver_name, receiver_phone, receiver_address,"
        " status, note, owner, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?,"
        " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_no,
            order_name,
            deal["customer_id"],
            deal_id,
            quote_id,
            summary_item["product_id"],
            summary_item["product_code_snapshot"],
            summary_item["product_name_snapshot"],
            summary_item["product_config_snapshot"],
            summary_item["product_type"],
            summary_item["model"],
            summary_item["spec"],
            amount,
            product_total,
            discount,
            payload.get("discount_reason") or None,
            product_payable,
            deposit,
            balance,
            mode,
            carrier_id,
            carrier_contact["id"] if carrier_contact else None,
            carrier_contact["name"] if carrier_contact else None,
            carrier_contact["phone"] if carrier_contact else None,
            fee,
            payload.get("tracking_number") or None,
            address_id,
            receiver_name,
            receiver_phone,
            receiver_address,
            order_status,
            payload.get("note") or None,
            deal["owner"],
            now,
            now,
        ),
    )
    order_id = int(cur.lastrowid or 0)
    if quote_id is not None:
        conn.execute(
            "UPDATE orders SET customer_confirmed_at = ?,"
            " customer_confirmation_note = ?, updated_at = ? WHERE id = ?",
            (
                quote["confirmed_at"],
                quote["confirmation_note"] or f"客户已确认报价单 {quote['quote_no']}",
                now,
                order_id,
            ),
        )

    auto_void_quotes = conn.execute(
        "SELECT id, quote_no, status FROM deal_quotes"
        " WHERE deal_id = ? AND is_delete = 0 AND status NOT IN ('void', 'confirmed')"
        " ORDER BY id",
        (deal_id,),
    ).fetchall()
    if auto_void_quotes:
        conn.execute(
            "UPDATE deal_quotes SET status = 'void', updated_at = ?"
            " WHERE deal_id = ? AND is_delete = 0 AND status NOT IN ('void', 'confirmed')",
            (now, deal_id),
        )
        sync_pending_quote_tags(conn, deal_id)
        add_entry(
            conn,
            object_type="deal",
            object_id=deal_id,
            kind="quote",
            customer_id=deal["customer_id"],
            deal_id=deal_id,
            quote_id=quote_id,
            content=(
                f"生成订单 {order_no}，系统自动作废未确认报价单 "
                + "、".join(row["quote_no"] for row in auto_void_quotes)
            ),
            detail={
                "event": "auto_void_for_order",
                "order_id": order_id,
                "order_no": order_no,
                "quotes": [
                    {
                        "id": int(row["id"]),
                        "quote_no": row["quote_no"],
                        "status_before": row["status"],
                        "status_after": "void",
                    }
                    for row in auto_void_quotes
                ],
            },
        )

    now_item = now_iso()
    for sort, item in enumerate(items):
        conn.execute(
            "INSERT INTO order_items (order_id, source_deal_item_id, source_quote_item_id, product_id,"
            " product_code_snapshot, product_name_snapshot, product_config_snapshot,"
            " product_type, model, drive_type, quantity, spec, production_spec,"
            " unit_price, amount, note, sort, created_at, updated_at,"
            " create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 0)",
            (
                order_id,
                None if quote_id is not None else item["id"],
                item["id"] if quote_id is not None else None,
                item["product_id"],
                item["product_code_snapshot"],
                item["product_name_snapshot"],
                item["product_config_snapshot"],
                item["product_type"],
                item["model"],
                item["drive_type"],
                item["quantity"],
                item["spec"],
                item["production_spec"],
                item["unit_price"],
                item["amount"],
                item["note"],
                sort,
                now_item,
                now_item,
            ),
        )

    if quote_id is not None:
        conn.execute(
            "UPDATE deal_quotes SET order_id = ?, updated_at = ? WHERE id = ?",
            (order_id, now, quote_id),
        )
        conn.execute(
            "UPDATE deals SET stage = 'won', closed_at = COALESCE(closed_at, ?), order_id = ?,"
            " locked_at = ?, amount = ?, updated_at = ? WHERE id = ?",
            (now_local_iso(), order_id, now_local_iso(), product_total, now, deal_id),
        )
    else:
        conn.execute(
            "UPDATE deals SET stage = 'confirm', closed_at = NULL, order_id = ?,"
            " locked_at = ?, updated_at = ? WHERE id = ?",
            (order_id, now_local_iso(), now, deal_id),
        )

    carrier_name = None
    if carrier_id:
        carrier_row = conn.execute(
            "SELECT name FROM carriers WHERE id = ?", (carrier_id,)
        ).fetchone()
        carrier_name = carrier_row["name"] if carrier_row else None
    contact_text = (
        f"/{carrier_contact['name']}({carrier_contact['phone']})"
        if carrier_contact
        else ""
    )
    logistics_text = (
        LOGISTICS_MODE_LABELS[mode]
        + (f"/{carrier_name}" if carrier_name else "")
        + contact_text
    )

    add_entry(
        conn,
        object_type="deal",
        object_id=deal_id,
        kind="order",
        customer_id=deal["customer_id"],
        deal_id=deal_id,
        quote_id=quote_id,
        content=(
            f"生成订单 {order_no}：产品 {product_total:,.2f}，优惠 {discount:,.2f}，"
            f"运费 {fee:,.2f}，应收 {amount:,.2f}；"
            + ("客户已确认报价单" if quote_id is not None else "待客户确认")
        ),
        detail={
            "order_id": order_id,
            "order_no": order_no,
            "product_total": product_total,
            "discount_amount": discount,
            "logistics_fee": fee,
            "carrier_contact_id": carrier_contact["id"] if carrier_contact else None,
            "carrier_contact_name": carrier_contact["name"] if carrier_contact else None,
            "carrier_contact_phone": carrier_contact["phone"] if carrier_contact else None,
            "amount": amount,
            "deposit": deposit,
            "balance": balance,
        },
    )
    conn.execute(
        "INSERT INTO order_status_log (order_id, from_status, to_status, event_type, note, detail,"
        " created_at) VALUES (?, NULL, ?, 'order', ?, ?, ?)",
        (
            order_id,
            order_status,
            f"生成订单 {order_no}：产品 ¥{product_total:,.2f}，优惠 ¥{discount:,.2f}，"
            f"运费 ¥{fee:,.2f}，应收 ¥{amount:,.2f}；"
            + ("客户已确认报价单" if quote_id is not None else "等待客户确认"),
            '{"order_no": "%s"}' % order_no,
            now,
        ),
    )

    # 意向升级：关联订单 → 至少「高」（客户与转化来源线索同步）
    upgrade_intent(conn, "customer", deal["customer_id"], "high")
    for _lead in conn.execute(
        "SELECT id FROM leads WHERE converted_customer_id = ? AND is_delete = 0",
        (deal["customer_id"],),
    ).fetchall():
        upgrade_intent(conn, "lead", _lead["id"], "high")

    deal_row = _deal_row(conn, deal_id)
    order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(deal_row), dict(order_row)


@router.post("/deals/{deal_id}/orders", response_model=dict)
def create_order(deal_id: int, payload: dict) -> dict:
    """生成订单（商机须到「待客户确认」；生成后等待客户确认）。"""
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
    """兼容旧前端：无参生成待确认订单（定金=全额、自提、运费 0）。

    定稿后的正路是 ``POST /deals/{id}/orders``（带定金 / 物流 / 收货信息）。
    """
    with db_conn() as conn:
        deal = _deal_row(conn, deal_id)
        if deal["order_id"] is not None:
            raise ApiError(status_code=409, code="order_exists", message="该商机已有订单")
        if deal["stage"] == "quote":
            conn.execute(
                "UPDATE deals SET stage = 'confirm', updated_at = ? WHERE id = ?",
                (now_iso(), deal_id),
            )
            add_entry(
                conn,
                object_type="deal",
                object_id=deal_id,
                kind="stage",
                customer_id=deal["customer_id"],
                deal_id=deal_id,
                content=f"阶段推进：{DEAL_STAGE_LABELS.get(deal['stage'], deal['stage'])} → 待客户确认",
                detail={"stage": {"from": deal["stage"], "to": "confirm"}},
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
        confirmed = conn.execute(
            "SELECT quote_no FROM deal_quotes"
            " WHERE deal_id = ? AND status = 'confirmed' AND is_delete = 0",
            (deal_id,),
        ).fetchone()
        if confirmed:
            raise ApiError(
                status_code=409,
                code="quote_already_confirmed",
                message=f"该商机已有客户确认的报价单 {confirmed['quote_no']}",
            )
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
