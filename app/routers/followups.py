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

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.db import IntegrityError, db_conn
from app.errors import ApiError
from app.followup_service import (
    clean_content,
    clean_next_date,
    create_follow_up_record,
    follow_up_to_item,
    photos_for,
    prepare_attachments,
    validate_object_type,
)
from app.lead_service import user_id_for_username
from app.models import (
    STAGES,
    FollowPhraseIn,
    FollowPhraseOut,
    FollowUpItemOut,
    FollowUpListOut,
    FollowUpOut,
)
from app.routers.auth import require_auth
from app.routers.leads import LIST_PAGE_SIZES
from app.security import now_iso

router = APIRouter(
    prefix="/api/crm",
    tags=["follow-ups"],
    dependencies=[Depends(require_auth)],
)

#: 跟进列表排序白名单（Ticket #16）：排序 SQL 一律来自这里的映射，绝不拼接前端传来的原始列名。
#: customer 走 LEFT JOIN 的 c.name；deal_stage 走 LEFT JOIN 的 d.stage。
_FOLLOWUP_SORT_SQL: dict[str, str] = {
    "customer": "c.name",
    "deal_stage": "d.stage",
    "content": "fu.content",
    "next_date": "fu.next_date",
    "created_at": "fu.created_at",
}

# 可为 NULL 的排序列：无论升降序都让其沉底（(expr IS NULL) ASC），否则升序时空值堆在最前面。
_FOLLOWUP_SORT_NULLABLE = frozenset({"customer", "deal_stage", "next_date"})


# ---------------- 入参清洗 ----------------


def _clean_phrase_content(raw: str | None) -> str:
    content = (raw or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="短语内容不能为空")
    if len(content) > 200:
        raise HTTPException(status_code=400, detail="短语内容最多 200 字")
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


# ---------------- 路由 ----------------


@router.get("/follow-up-phrases", response_model=list[FollowPhraseOut])
def list_follow_phrases(
    object_type: str = Query(..., description="lead/customer/deal/order/aftersale"),
) -> list[FollowPhraseOut]:
    """返回某个业务对象自己的常用短语集。"""
    validate_object_type(object_type)
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, object_type, content, sort, created_at
            FROM follow_up_phrases
            WHERE object_type = ? AND is_delete = 0
            ORDER BY sort, id
            """,
            (object_type,),
        ).fetchall()
    return [FollowPhraseOut(**dict(row)) for row in rows]


@router.post(
    "/follow-up-phrases",
    response_model=FollowPhraseOut,
    status_code=201,
)
def create_follow_phrase(payload: FollowPhraseIn) -> FollowPhraseOut:
    """新增常用短语；同一短语可在不同业务对象下各存一份。"""
    content = _clean_phrase_content(payload.content)
    created_at = now_iso()
    try:
        with db_conn() as conn:
            duplicate = conn.execute(
                """
                SELECT 1 FROM follow_up_phrases
                WHERE object_type = ? AND content = ? AND is_delete = 0
                """,
                (payload.object_type, content),
            ).fetchone()
            if duplicate is not None:
                raise HTTPException(status_code=409, detail="这个短语已经存在")

            next_sort = conn.execute(
                """
                SELECT COALESCE(MAX(sort), 0) + 1
                FROM follow_up_phrases
                WHERE object_type = ?
                """,
                (payload.object_type,),
            ).fetchone()[0]
            cur = conn.execute(
                """
                INSERT INTO follow_up_phrases
                    (object_type, content, sort, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.object_type,
                    content,
                    int(next_sort or 1),
                    created_at,
                    created_at,
                ),
            )
            phrase_id = int(cur.lastrowid or 0)
            row = conn.execute(
                """
                SELECT id, object_type, content, sort, created_at
                FROM follow_up_phrases
                WHERE id = ? AND is_delete = 0
                """,
                (phrase_id,),
            ).fetchone()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="这个短语已经存在") from None

    if row is None:
        raise HTTPException(status_code=500, detail="短语保存失败")
    return FollowPhraseOut(**dict(row))


@router.delete("/follow-up-phrases/{phrase_id}")
def delete_follow_phrase(phrase_id: int) -> dict:
    """软删除常用短语；已插入跟进正文的文字不受影响。"""
    with db_conn() as conn:
        phrase = conn.execute(
            """
            SELECT object_type FROM follow_up_phrases
            WHERE id = ? AND is_delete = 0
            """,
            (phrase_id,),
        ).fetchone()
        if phrase is None:
            raise HTTPException(status_code=404, detail="常用短语不存在")
        conn.execute(
            """
            UPDATE follow_up_phrases
            SET is_delete = 1, updated_at = ?
            WHERE id = ? AND is_delete = 0
            """,
            (now_iso(), phrase_id),
        )
    return {"ok": True, "id": phrase_id}


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
    files: list[UploadFile] = File(default=[], description="任意类型附件（≤20 个，单个 ≤20MB）"),
    username: str = Depends(require_auth),
) -> FollowUpItemOut:
    """页面建跟进；校验和写入复用外部 API 的同一服务。"""
    # V1 兼容：只传 customer_id / deal_id 时推导 object_type / object_id
    if not object_type:
        if deal_id:
            object_type, object_id = "deal", deal_id
        elif customer_id:
            object_type, object_id = "customer", customer_id
        else:
            raise HTTPException(status_code=400, detail="object_type 必填")
    validate_object_type(object_type)

    object_id_value = _clean_optional_int(object_id, "object_id")
    if object_id_value is None:
        raise HTTPException(status_code=400, detail="object_id 必填")
    customer_id_value = _clean_optional_int(customer_id, "customer_id")
    deal_id_value = _clean_optional_int(deal_id, "deal_id")
    quote_id_value = _clean_optional_int(quote_id, "quote_id")

    content_value = clean_content(content)
    next_date_value = clean_next_date(next_date)
    stage_value = _clean_stage(stage)
    method_value = (method or "").strip()
    intent_level_value = (intent_level or "").strip()
    prepared = await prepare_attachments([*(photos or []), *(files or [])])
    with db_conn() as conn:
        return create_follow_up_record(
            conn,
            object_type=object_type,
            object_id=object_id_value,
            content=content_value,
            method=method_value,
            next_date=next_date_value,
            attachments=prepared,
            created_by=user_id_for_username(conn, username),
            intent_level=intent_level_value,
            stage=stage_value,
            quote_id=quote_id_value,
            customer_id_hint=customer_id_value,
            deal_id_hint=deal_id_value,
        )


@router.get("/follow-ups", response_model=FollowUpListOut)
def list_follow_ups(
    customer_id: int | None = Query(default=None, gt=0),
    deal_id: int | None = Query(default=None, gt=0),
    object_type: str | None = Query(default=None),
    object_id: int | None = Query(default=None, gt=0),
    include_system: bool = Query(
        default=False, description="true = 连系统履历一起返回（创建/编辑/阶段变更/生成订单等）"
    ),
    page: int = Query(default=1),
    size: int = Query(default=20),
    sort: str | None = Query(default=None),
    order: str = Query(default="desc"),
) -> FollowUpListOut:
    """按客户/商机/对象类型/对象ID过滤；不带过滤=全量分页（新的在前），每条带照片数与照片列表。

    默认只返回用户记的**真实跟进**（kind='follow'）——与 V1 语义一致；
    跟进页要看完整履历（含系统事件）时传 ``include_system=true``。

    分页/排序（Ticket #16，复用 Ticket #9/#13 同一套校验口径）：size 白名单
    ``LIST_PAGE_SIZES``，sort 白名单见 ``_FOLLOWUP_SORT_SQL``；非法 page/size/sort/order
    一律 400，排序 SQL 只走白名单映射。不传 sort 时按记录时间倒序、id 倒序。
    """
    if page < 1:
        raise ApiError(status_code=400, code="invalid_page", message="page 必须 >= 1")
    if size not in LIST_PAGE_SIZES:
        raise ApiError(
            status_code=400,
            code="invalid_page_size",
            message=f"size 必须是 {'/'.join(str(s) for s in LIST_PAGE_SIZES)} 之一",
        )
    sort = sort or None  # 显式传空串等同未传，走默认排序
    if sort is not None and sort not in _FOLLOWUP_SORT_SQL:
        raise ApiError(
            status_code=400,
            code="invalid_sort",
            message=f"sort 只支持 {'/'.join(_FOLLOWUP_SORT_SQL)}",
        )
    if order not in ("asc", "desc"):
        raise ApiError(status_code=400, code="invalid_order", message="order 只支持 asc/desc")

    if sort:
        expr = _FOLLOWUP_SORT_SQL[sort]
        dir_sql = "ASC" if order == "asc" else "DESC"
        # 显式排序：稳定次键固定 id DESC；可空列先排 NULL 沉底（升/降序都沉底）。
        if sort in _FOLLOWUP_SORT_NULLABLE:
            order_sql = f"({expr} IS NULL) ASC, {expr} {dir_sql}, fu.id DESC"
        else:
            order_sql = f"{expr} {dir_sql}, fu.id DESC"
    else:
        order_sql = "fu.created_at DESC, fu.id DESC"

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

    where_sql = " AND " + " AND ".join(where_parts) if where_parts else ""
    with db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM follow_ups fu WHERE fu.is_delete = 0{where_sql}",
            params,
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT fu.id, fu.customer_id, fu.deal_id, fu.quote_id, fu.method, fu.kind, fu.content, fu.next_date,
                   fu.detail, fu.created_by, fu.created_at, fu.object_type, fu.object_id,
                   c.name AS customer_name, d.stage AS deal_stage,
                   q.quote_no, q.title AS quote_title
            FROM follow_ups fu
            LEFT JOIN customers c ON c.id = fu.customer_id
            LEFT JOIN deals d ON d.id = fu.deal_id
            LEFT JOIN deal_quotes q ON q.id = fu.quote_id
            WHERE fu.is_delete = 0{where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, size, (page - 1) * size],
        ).fetchall()
        photos_map = photos_for(conn, [row["id"] for row in rows])

    return FollowUpListOut(
        items=[
            follow_up_to_item(row, photos_map.get(row["id"], []))
            for row in rows
        ],
        total=total,
        page=page,
        size=size,
    )


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
