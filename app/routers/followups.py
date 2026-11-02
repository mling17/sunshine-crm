"""跟进记录 + 照片（multipart）。

设计要点（已拍板，别再改）：
- 照片存本地 ``uploads/YYYY/MM/DD/<uuid>.<ext>``，一条跟进 **1~3 张**，上限由应用层卡
  （超了 400，且**不留任何**跟进行/文件）；``storage_key`` 只存相对上传根的路径。
- 记跟进时可选带 ``stage`` + ``deal_id``，顺手改商机阶段 —— 她不想在商机页单独点一圈。
  阶段语义与 ``deals.py`` 完全一致：进 ``won`` 置 ``closed_at``（本地时间），从 ``won``
  移出清空，否则只改 stage。
- 删跟进只删 ``follow_ups``（外键级联清 ``attachments`` 行）；物理文件留给备份清理，
  不做逐张删除 —— 单用户量小，误删还能从备份里捞回来。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app import labels
from app.db import db_conn
from app.errors import ApiError
from app.models import (
    MAX_PHOTOS,
    STAGES,
    AttachmentOut,
    FollowUpItemOut,
    FollowUpOut,
)
from app.routers.auth import require_auth
from app.security import now_iso, now_local_iso
from app.storage import MAX_PHOTO_BYTES, ext_and_mime, new_storage_key, save_photo

router = APIRouter(
    prefix="/api/crm",
    tags=["follow-ups"],
    dependencies=[Depends(require_auth)],
)


# ---------------- 入参清洗 ----------------


def _clean_content(raw: str | None) -> str:
    content = (raw or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="跟进内容不能为空")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="跟进内容最多 2000 字")
    return content


def _clean_optional_int(raw: str | None, field: str) -> int | None:
    """multipart 里的可选数字：空串/null 当没填，非数字 400（而不是 pydantic 的 422）。"""
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} 必须是整数") from None
    if parsed <= 0:
        raise HTTPException(status_code=400, detail=f"{field} 必须是正整数")
    return parsed


def _clean_next_date(raw: str | None) -> str | None:
    """只收 ``YYYY-MM-DD``；格式错/日期不存在（如 2 月 30）一律 400。

    不做「过去日期」限制 —— 补录昨天的拜访也是真实场景。
    """
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="next_date 格式必须是 YYYY-MM-DD"
        ) from None
    return parsed.strftime("%Y-%m-%d")


def _clean_stage(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value not in STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"非法阶段 {value!r}，合法值：" + "、".join(STAGES),
        )
    return value


async def _read_photos(files: list[UploadFile]) -> list[tuple[str, str, str, bytes]]:
    """读完所有附件并校验（PLANNER-V3 §6.5）。

    允许：图片 / PDF / Excel / Word / CSV / CAD / ZIP / TXT；单个 ≤20MB；一条跟进 ≤10 个。
    先全部读完再落盘/写库，保证 400 时磁盘和 DB 都干净（不留半截数据）。
    """
    from app.storage import MAX_FILE_BYTES, MAX_FILES_PER_FOLLOWUP, ext_and_mime_any

    prepared: list[tuple[str, str, str, bytes]] = []
    for upload in files or []:
        data = await upload.read()
        filename = (upload.filename or "").strip()
        # 浏览器空 file input 会送一个 filename 为空、内容为空的条目，直接忽略
        if not filename and not data:
            continue
        if not data:
            raise HTTPException(status_code=400, detail=f"附件 {filename} 是空文件")
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"附件 {filename} 超过 {MAX_FILE_BYTES // (1024 * 1024)}MB",
            )
        ext, mime = ext_and_mime_any(filename)
        prepared.append((filename or f"file{ext}", mime, ext, data))

    if len(prepared) > MAX_FILES_PER_FOLLOWUP:
        raise HTTPException(
            status_code=400,
            detail=f"一条跟进最多 {MAX_FILES_PER_FOLLOWUP} 个附件，本次选了 {len(prepared)} 个",
        )
    return prepared


# ---------------- 查询helper ----------------


def _photos_for(conn, follow_up_ids: list[int]) -> dict[int, list[AttachmentOut]]:
    """一次查回多条跟进的照片，避免列表页 N+1。"""
    if not follow_up_ids:
        return {}
    placeholders = ", ".join("?" for _ in follow_up_ids)
    rows = conn.execute(
        f"""
        SELECT id, follow_up_id, file_name, mime_type, size
        FROM attachments
        WHERE follow_up_id IN ({placeholders}) AND is_delete = 0
        ORDER BY id
        """,
        follow_up_ids,
    ).fetchall()

    grouped: dict[int, list[AttachmentOut]] = {}
    for row in rows:
        grouped.setdefault(row["follow_up_id"], []).append(
            AttachmentOut(
                **dict(row), url=f"/api/crm/attachments/{row['id']}"
            )
        )
    return grouped


def _to_item(row, photos: list[AttachmentOut]) -> FollowUpItemOut:
    data = dict(row)
    raw_detail = data.get("detail")
    if isinstance(raw_detail, str) and raw_detail:
        try:
            data["detail"] = json.loads(raw_detail)
        except (TypeError, ValueError):
            data["detail"] = None
    # 跟进方式的中文也走字典（follow_method 是 A 类，可改名）
    data["method_label"] = labels.follow_method(data.get("method"))
    return FollowUpItemOut(
        **data, photo_count=len(photos), photos=photos
    )


def _fetch_item(conn, follow_up_id: int) -> FollowUpItemOut:
    row = conn.execute(
        """
        SELECT fu.id, fu.customer_id, fu.deal_id, fu.quote_id, fu.object_type, fu.object_id, fu.method, fu.kind,
               fu.content, fu.detail, fu.next_date, fu.created_at,
               c.name AS customer_name, d.stage AS deal_stage,
               q.quote_no, q.title AS quote_title
        FROM follow_ups fu
        LEFT JOIN customers c ON c.id = fu.customer_id
        LEFT JOIN deals d ON d.id = fu.deal_id
        LEFT JOIN deal_quotes q ON q.id = fu.quote_id
        WHERE fu.id = ? AND fu.is_delete = 0
        """,
        (follow_up_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="跟进记录不存在")
    return _to_item(row, _photos_for(conn, [follow_up_id]).get(follow_up_id, []))


def _apply_stage(conn, deal_id: int, old_stage: str, new_stage: str) -> None:
    """与 ``deals.py`` 的阶段口径保持一致：won 写 closed_at，移出 won 清空。"""
    if new_stage == old_stage:
        return
    now = now_iso()
    if new_stage == "won":
        conn.execute(
            "UPDATE deals SET stage = ?, closed_at = ?, updated_at = ? WHERE id = ?",
            (new_stage, now_local_iso(), now, deal_id),
        )
    elif old_stage == "won":
        conn.execute(
            "UPDATE deals SET stage = ?, closed_at = NULL, updated_at = ? WHERE id = ?",
            (new_stage, now, deal_id),
        )
    else:
        conn.execute(
            "UPDATE deals SET stage = ?, updated_at = ? WHERE id = ?",
            (new_stage, now, deal_id),
        )


# ---------------- 跟进对象类型校验 ----------------


def _validate_object_type(object_type: str) -> None:
    """校验对象类型是否合法"""
    valid_types = ["lead", "customer", "deal", "order", "aftersale"]
    if object_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"非法对象类型 {object_type!r}")


def _check_deal_frozen(conn, deal_id: int) -> None:
    """检查商机是否被冻结"""
    deal = conn.execute(
        "SELECT stage, order_id FROM deals WHERE id = ? AND is_delete = 0",
        (deal_id,),
    ).fetchone()
    if deal is None:
        raise HTTPException(status_code=404, detail="商机不存在")
    
    # 检查是否为冻结状态
    if deal["order_id"] is not None or deal["stage"] == "lost":
        raise ApiError(
            status_code=409,
            code="deal_frozen",
            message="商机已赢单或已流失，无法添加跟进"
        )


# ---------------- 路由 ----------------


@router.post("/follow-ups", response_model=FollowUpItemOut)
async def create_follow_up(
    object_type: str | None = Form(default=None, description="对象类型（V1 兼容时可省略）"),
    object_id: str | None = Form(default=None, description="对象ID（V1 兼容时可省略）"),
    customer_id: str | None = Form(default=None, description="V1 兼容：客户ID"),
    deal_id: str | None = Form(default=None, description="V1 兼容：商机ID"),
    quote_id: str | None = Form(default=None, description="可关联当前商机的报价单"),
    content: str = Form(..., description="跟进内容"),
    method: str | None = Form(default=None),
    next_date: str | None = Form(default=None),
    intent_level: str | None = Form(default=None),
    stage: str | None = Form(default=None),
    photos: list[UploadFile] = File(default=[], description="兼容旧前端：图片附件"),
    files: list[UploadFile] = File(default=[], description="任意类型附件（≤10 个，单个 ≤20MB）"),
) -> FollowUpItemOut:
    """建跟进（multipart）。照片 0~3 张；带 stage+deal_id 顺手改阶段。

    支持多种对象类型挂载：线索/客户/商机/订单/售后
    """
    # V1 兼容：只传 customer_id / deal_id 时推导 object_type / object_id
    if not object_type:
        if deal_id:
            object_type, object_id = "deal", deal_id
        elif customer_id:
            object_type, object_id = "customer", customer_id
        else:
            raise HTTPException(status_code=400, detail="object_type 必填")
    # V1 兼容：客户 + 商机同时传时先校验归属（计划 §2.3：deal 必须属于该客户）
    if customer_id and deal_id:
        with db_conn() as _c:
            _row = _c.execute(
                "SELECT customer_id FROM deals WHERE id = ? AND is_delete = 0",
                (int(deal_id),),
            ).fetchone()
            if _row is None:
                raise HTTPException(status_code=404, detail="商机不存在")
            if int(_row["customer_id"]) != int(customer_id):
                raise HTTPException(status_code=400, detail="商机不属于该客户")
    # 校验对象类型
    _validate_object_type(object_type)
    
    # 清洗参数
    object_id_value = _clean_optional_int(object_id, "object_id")
    if object_id_value is None:
        raise HTTPException(status_code=400, detail="object_id 必填")
    
    content_value = _clean_content(content)
    next_date_value = _clean_next_date(next_date)
    stage_value = _clean_stage(stage)
    method_value = (method or "").strip()
    intent_level_value = (intent_level or "").strip()
    quote_id_value = _clean_optional_int(quote_id, "quote_id")
    if quote_id_value is not None:
        with db_conn() as _quote_conn:
            quote_row = _quote_conn.execute(
                "SELECT deal_id FROM deal_quotes WHERE id = ? AND is_delete = 0",
                (quote_id_value,),
            ).fetchone()
        if quote_row is None:
            raise HTTPException(status_code=404, detail="报价单不存在")
        expected_deal_id = int(deal_id) if deal_id else (
            object_id_value if object_type == "deal" else None
        )
        if expected_deal_id is None or int(quote_row["deal_id"]) != expected_deal_id:
            raise HTTPException(status_code=400, detail="报价单不属于当前商机")
    
    # V1 兼容：带 deal_id 时校验存在性与归属（计划 §2.3 / §5.4）
    deal_row_checked = None
    if deal_id:
        with db_conn() as _conn:
            deal_row_checked = _conn.execute(
                "SELECT id, customer_id, stage FROM deals"
                " WHERE id = ? AND is_delete = 0",
                (int(deal_id),),
            ).fetchone()
        if deal_row_checked is None:
            raise HTTPException(status_code=404, detail="商机不存在")
        if object_type == "customer" and int(deal_row_checked["customer_id"]) != object_id_value:
            raise HTTPException(status_code=400, detail="商机不属于该客户")

    # 验证对象类型和ID的合法性
    with db_conn() as conn:
        if object_type == "lead":
            # 检查线索是否存在
            lead = conn.execute(
                "SELECT status FROM leads WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if lead is None:
                raise HTTPException(status_code=404, detail="线索不存在")
            # 检查线索是否已终结
            if lead["status"] in ("converted", "invalid"):
                raise ApiError(
                    status_code=409,
                    code="lead_closed",
                    message="线索已转化或已失效，无法添加跟进"
                )
        elif object_type == "customer":
            # 检查客户是否存在
            customer = conn.execute(
                "SELECT id FROM customers WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if customer is None:
                raise HTTPException(status_code=404, detail="客户不存在")
        elif object_type == "deal":
            # 检查商机是否存在
            deal = conn.execute(
                "SELECT id, stage, order_id FROM deals WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if deal is None:
                raise HTTPException(status_code=404, detail="商机不存在")
            # 检查商机是否被冻结
            if deal["order_id"] is not None or deal["stage"] == "lost":
                raise ApiError(
                    status_code=409,
                    code="deal_frozen",
                    message="商机已赢单或已流失，无法添加跟进"
                )
        elif object_type == "order":
            # 已完成订单只读；后续沟通必须落到该订单的售后单。
            order = conn.execute(
                "SELECT id, status, order_no FROM orders WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="订单不存在")
            if order["status"] == "completed":
                raise ApiError(
                    status_code=409,
                    code="order_completed_use_aftersale",
                    message="订单已完成，不能继续跟进；如需继续处理，请创建售后单",
                )
        elif object_type == "aftersale":
            # 检查售后单是否存在 + 状态守卫（PLANNER-V3 §6.4）
            aftersale = conn.execute(
                "SELECT id, status FROM aftersales WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if aftersale is None:
                raise HTTPException(status_code=404, detail="售后单不存在")
            if aftersale["status"] == "done":
                raise ApiError(
                    status_code=409,
                    code="aftersale_closed",
                    message="该售后单已完成，不能再添加跟进记录",
                )

    prepared = await _read_photos([*(photos or []), *(files or [])])

    created_at = now_iso()
    with db_conn() as conn:
        # 先获取客户ID（用于兼容V1参数）
        customer_id_value = None
        deal_id_value = None
        
        # 根据对象类型获取客户ID和商机ID
        if deal_id and object_type != "deal":
            # V1 兼容：客户跟进同时挂到商机（已校验归属）
            deal_id_value = int(deal_id)
        if object_type == "lead":
            # 线索不需要customer_id，但可以获取相关信息
            pass
        elif object_type == "customer":
            customer_id_value = object_id_value
        elif object_type == "deal":
            # 获取商机对应的客户ID
            deal = conn.execute(
                "SELECT customer_id FROM deals WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if deal:
                customer_id_value = deal["customer_id"]
            deal_id_value = object_id_value
        elif object_type == "order":
            # 获取订单对应的客户ID
            order = conn.execute(
                "SELECT customer_id FROM orders WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if order:
                customer_id_value = order["customer_id"]
        elif object_type == "aftersale":
            # 获取售后单对应的客户ID
            aftersale = conn.execute(
                "SELECT customer_id FROM aftersales WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if aftersale:
                customer_id_value = aftersale["customer_id"]

        # 插入跟进记录
        cur = conn.execute(
            """
            INSERT INTO follow_ups
                (object_type, object_id, customer_id, deal_id, quote_id, method, kind, content, next_date,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'follow', ?, ?, ?)
            """,
            (
                object_type,
                object_id_value,
                customer_id_value,
                deal_id_value,
                quote_id_value,
                method_value,
                content_value,
                next_date_value,
                created_at,
            ),
        )
        follow_up_id = int(cur.lastrowid or 0)

        # 线索产生第一条真实跟进后，状态由「新线索」进入「跟进中」。
        # 转化/失效是终态，前面已经拦截，这里只处理仍在流程中的线索。
        if object_type == "lead":
            current_lead = conn.execute(
                "SELECT status FROM leads WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if current_lead and current_lead["status"] == "new":
                conn.execute(
                    "UPDATE leads SET status = 'following', updated_at = ? WHERE id = ?",
                    (created_at, object_id_value),
                )
                from app.timeline import add_entry as _add_entry
                _add_entry(
                    conn,
                    object_type="lead",
                    object_id=object_id_value,
                    kind="change",
                    content="状态更新：新线索 → 跟进中",
                )
            else:
                conn.execute(
                    "UPDATE leads SET updated_at = ? WHERE id = ?",
                    (created_at, object_id_value),
                )

        # 售后：待处理遇到跟进 → 自动进入「处理中」（定稿 v2.4 #9 / PLANNER-V3 §6.4）
        if object_type == "aftersale":
            current = conn.execute(
                "SELECT status FROM aftersales WHERE id = ? AND is_delete = 0",
                (object_id_value,),
            ).fetchone()
            if current and current["status"] == "pending":
                conn.execute(
                    "UPDATE aftersales SET status = 'processing', updated_at = ? WHERE id = ?",
                    (created_at, object_id_value),
                )
                conn.execute(
                    "INSERT INTO aftersale_status_log (aftersale_id, from_status, to_status, note,"
                    " created_at) VALUES (?, 'pending', 'processing', ?, ?)",
                    (object_id_value, "记跟进后自动进入处理中", created_at),
                )
                from app.timeline import add_entry as _add_aftersale_entry

                _add_aftersale_entry(
                    conn,
                    object_type="aftersale",
                    object_id=object_id_value,
                    kind="stage",
                    content="状态变更：待处理 → 处理中",
                    detail={"from": "pending", "to": "processing"},
                )

        # 处理照片
        for file_name, mime, ext, data in prepared:
            storage_key = new_storage_key(ext)
            save_photo(storage_key, data)
            conn.execute(
                """
                INSERT INTO attachments
                    (object_type, object_id, follow_up_id, storage_key, file_name, mime_type, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (object_type, object_id_value, follow_up_id, storage_key, file_name, mime, len(data), created_at),
            )

        # 如果有意图等级，则更新对应对象
        if intent_level_value:
            if object_type == "lead" or object_type == "customer":
                # 更新线索或客户意图等级
                if object_type == "lead":
                    conn.execute(
                        "UPDATE leads SET intent_level = ?, updated_at = ? WHERE id = ?",
                        (intent_level_value, created_at, object_id_value),
                    )
                elif object_type == "customer":
                    conn.execute(
                        "UPDATE customers SET intent_level = ?, updated_at = ? WHERE id = ?",
                        (intent_level_value, created_at, object_id_value),
                    )

        # 如果有阶段并且是商机，更新阶段
        if stage_value and deal_id_value is not None:
            # 获取商机原始阶段
            deal = conn.execute(
                "SELECT stage FROM deals WHERE id = ? AND is_delete = 0",
                (deal_id_value,),
            ).fetchone()
            old_stage = deal["stage"] if deal else ""
            _apply_stage(conn, deal_id_value, old_stage, stage_value)

        item = _fetch_item(conn, follow_up_id)

    return item


@router.get("/follow-ups", response_model=list[FollowUpItemOut])
def list_follow_ups(
    customer_id: int | None = Query(default=None, gt=0),
    deal_id: int | None = Query(default=None, gt=0),
    object_type: str | None = Query(default=None),
    object_id: int | None = Query(default=None, gt=0),
    include_system: bool = Query(
        default=False, description="true = 连系统履历一起返回（创建/编辑/阶段变更/生成订单等）"
    ),
) -> list[FollowUpItemOut]:
    """按客户/商机/对象类型/对象ID过滤；不带过滤=全量（新的在前），每条带照片数与照片列表。

    默认只返回用户记的**真实跟进**（kind='follow'）——与 V1 语义一致；
    跟进页要看完整履历（含系统事件）时传 ``include_system=true``。
    """
    where_parts: list[str] = []
    params: list[object] = []
    if not include_system:
        where_parts.append("(fu.kind IS NULL OR fu.kind = 'follow')")
    
    if customer_id is not None:
        where_parts.append("fu.customer_id = ?")
        params.append(customer_id)
    if deal_id is not None:
        where_parts.append("fu.deal_id = ?")
        params.append(deal_id)
    if object_type is not None:
        where_parts.append("fu.object_type = ?")
        params.append(object_type)
    if object_id is not None:
        where_parts.append("fu.object_id = ?")
        params.append(object_id)

    with db_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT fu.id, fu.customer_id, fu.deal_id, fu.quote_id, fu.method, fu.kind, fu.content, fu.next_date,
                   fu.detail, fu.created_at, fu.object_type, fu.object_id,
                   c.name AS customer_name, d.stage AS deal_stage,
                   q.quote_no, q.title AS quote_title
            FROM follow_ups fu
            LEFT JOIN customers c ON c.id = fu.customer_id
            LEFT JOIN deals d ON d.id = fu.deal_id
            LEFT JOIN deal_quotes q ON q.id = fu.quote_id
            WHERE fu.is_delete = 0
            {" AND " + " AND ".join(where_parts) if where_parts else ""}
            ORDER BY fu.created_at DESC, fu.id DESC
            """,
            params,
        ).fetchall()
        photos_map = _photos_for(conn, [row["id"] for row in rows])

    return [
        _to_item(row, photos_map.get(row["id"], []))
        for row in rows
    ]


@router.get("/follow-ups/materials")
def list_materials(
    object_type: str = Query(..., description="customer / deal / lead / aftersale"),
    object_id: int = Query(..., gt=0),
    deep: bool = Query(default=False, description="客户：连其商机/售后的附件一起汇总"),
) -> list[dict]:
    """资料汇总卡（PLANNER-V3 §5.7）：某对象所有跟进的附件，时间倒序。

    客户的 ``deep=true`` 会把名下商机、售后单的跟进附件也并进来。
    """
    targets: list[tuple[str, int]] = [(object_type, object_id)]
    with db_conn() as conn:
        if deep and object_type == "customer":
            for row in conn.execute(
                "SELECT id FROM deals WHERE customer_id = ? AND is_delete = 0",
                (object_id,),
            ).fetchall():
                targets.append(("deal", int(row["id"])))
            for row in conn.execute(
                "SELECT id FROM aftersales WHERE customer_id = ? AND is_delete = 0",
                (object_id,),
            ).fetchall():
                targets.append(("aftersale", int(row["id"])))

        rows = []
        for otype, oid in targets:
            rows.extend(
                conn.execute(
                    "SELECT a.id, a.file_name, a.mime_type, a.size, a.created_at,"
                    "       f.id AS follow_up_id, f.content"
                    "  FROM attachments a JOIN follow_ups f ON f.id = a.follow_up_id"
                    " WHERE f.object_type = ? AND f.object_id = ?"
                    " AND f.is_delete = 0 AND a.is_delete = 0"
                    " ORDER BY datetime(a.created_at) DESC, a.id DESC",
                    (otype, oid),
                ).fetchall()
            )

    rows.sort(key=lambda r: (str(r["created_at"]), r["id"]), reverse=True)
    return [
        {
            "id": r["id"],
            "name": r["file_name"],
            "mime": r["mime_type"],
            "size": r["size"],
            "is_image": str(r["mime_type"] or "").startswith("image/"),
            "url": f"/api/crm/attachments/{r['id']}",
            "at": r["created_at"],
            "content": r["content"],
            "follow_up_id": r["follow_up_id"],
        }
        for r in rows
    ]


@router.delete("/follow-ups/{follow_up_id}")
def delete_follow_up(follow_up_id: int) -> dict:
    """删跟进；``attachments`` 行由外键级联清掉，磁盘文件留给备份清理。"""
    with db_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM follow_ups WHERE id = ? AND is_delete = 0",
            (follow_up_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="跟进记录不存在")
        now = now_iso()
        conn.execute(
            "UPDATE follow_ups SET is_delete = 1, update_time = ? WHERE id = ?",
            (now, follow_up_id),
        )
        conn.execute(
            "UPDATE attachments SET is_delete = 1, update_time = ?"
            " WHERE follow_up_id = ?",
            (now, follow_up_id),
        )

    return {"ok": True, "id": follow_up_id}
