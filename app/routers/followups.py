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

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.db import db_conn
from app.models import (
    MAX_PHOTOS,
    STAGES,
    AttachmentOut,
    FollowUpItemOut,
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


async def _read_photos(photos: list[UploadFile]) -> list[tuple[str, str, str, bytes]]:
    """读完所有照片并校验：空条目跳过、非图片 400、单张超 20MB 400、总数 >3 400。

    先全部读完再落盘/写库，保证 400 时磁盘和 DB 都干净（不留半截数据）。
    """
    prepared: list[tuple[str, str, str, bytes]] = []
    for upload in photos or []:
        data = await upload.read()
        filename = (upload.filename or "").strip()
        # 浏览器空 file input 会送一个 filename 为空、内容为空的条目，直接忽略
        if not filename and not data:
            continue
        ext, mime = ext_and_mime(filename, upload.content_type)
        if not data:
            raise HTTPException(status_code=400, detail=f"照片 {filename} 是空文件")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"照片 {filename} 超过 {MAX_PHOTO_BYTES // (1024 * 1024)}MB",
            )
        prepared.append((filename or f"photo{ext}", mime, ext, data))

    if len(prepared) > MAX_PHOTOS:
        raise HTTPException(
            status_code=400, detail=f"一条跟进最多 {MAX_PHOTOS} 张照片"
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
        FROM attachments WHERE follow_up_id IN ({placeholders}) ORDER BY id
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
    return FollowUpItemOut(
        **dict(row), photo_count=len(photos), photos=photos
    )


def _fetch_item(conn, follow_up_id: int) -> FollowUpItemOut:
    row = conn.execute(
        """
        SELECT fu.id, fu.customer_id, fu.deal_id, fu.content, fu.next_date, fu.created_at,
               c.name AS customer_name, d.stage AS deal_stage
        FROM follow_ups fu
        JOIN customers c ON c.id = fu.customer_id
        LEFT JOIN deals d ON d.id = fu.deal_id
        WHERE fu.id = ?
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


# ---------------- 路由 ----------------


@router.post("/follow-ups", response_model=FollowUpItemOut)
async def create_follow_up(
    customer_id: str = Form(..., description="客户 id"),
    content: str = Form(..., description="跟进内容"),
    deal_id: str | None = Form(default=None),
    next_date: str | None = Form(default=None),
    stage: str | None = Form(default=None),
    photos: list[UploadFile] = File(default=[]),
) -> FollowUpItemOut:
    """建跟进（multipart）。照片 0~3 张；带 stage+deal_id 顺手改阶段。"""
    customer_id_value = _clean_optional_int(customer_id, "customer_id")
    if customer_id_value is None:
        raise HTTPException(status_code=400, detail="customer_id 必填")
    deal_id_value = _clean_optional_int(deal_id, "deal_id")
    content_value = _clean_content(content)
    next_date_value = _clean_next_date(next_date)
    stage_value = _clean_stage(stage)

    prepared = await _read_photos(photos)

    created_at = now_iso()
    with db_conn() as conn:
        customer = conn.execute(
            "SELECT id, name FROM customers WHERE id = ?", (customer_id_value,)
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="客户不存在")

        old_stage: str | None = None
        if deal_id_value is not None:
            deal = conn.execute(
                "SELECT id, customer_id, stage FROM deals WHERE id = ?",
                (deal_id_value,),
            ).fetchone()
            if deal is None:
                raise HTTPException(status_code=404, detail="商机不存在")
            if deal["customer_id"] != customer_id_value:
                raise HTTPException(
                    status_code=400, detail="商机不属于该客户"
                )
            old_stage = deal["stage"]

        cur = conn.execute(
            """
            INSERT INTO follow_ups (customer_id, deal_id, content, next_date, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                customer_id_value,
                deal_id_value,
                content_value,
                next_date_value,
                created_at,
            ),
        )
        follow_up_id = int(cur.lastrowid or 0)

        for file_name, mime, ext, data in prepared:
            storage_key = new_storage_key(ext)
            save_photo(storage_key, data)
            conn.execute(
                """
                INSERT INTO attachments
                    (follow_up_id, storage_key, file_name, mime_type, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (follow_up_id, storage_key, file_name, mime, len(data), created_at),
            )

        if stage_value and deal_id_value is not None:
            _apply_stage(conn, deal_id_value, old_stage or "", stage_value)

        item = _fetch_item(conn, follow_up_id)

    return item


@router.get("/follow-ups", response_model=list[FollowUpItemOut])
def list_follow_ups(
    customer_id: int | None = Query(default=None, gt=0),
    deal_id: int | None = Query(default=None, gt=0),
) -> list[FollowUpItemOut]:
    """按客户/商机过滤；不带过滤=全量（新的在前），每条带照片数与照片列表。"""
    where_parts: list[str] = []
    params: list[object] = []
    if customer_id is not None:
        where_parts.append("fu.customer_id = ?")
        params.append(customer_id)
    if deal_id is not None:
        where_parts.append("fu.deal_id = ?")
        params.append(deal_id)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    with db_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT fu.id, fu.customer_id, fu.deal_id, fu.content, fu.next_date, fu.created_at,
                   c.name AS customer_name, d.stage AS deal_stage
            FROM follow_ups fu
            JOIN customers c ON c.id = fu.customer_id
            LEFT JOIN deals d ON d.id = fu.deal_id
            {where_sql}
            ORDER BY fu.created_at DESC, fu.id DESC
            """,
            params,
        ).fetchall()
        photos_map = _photos_for(conn, [row["id"] for row in rows])

    return [
        _to_item(row, photos_map.get(row["id"], []))
        for row in rows
    ]


@router.delete("/follow-ups/{follow_up_id}")
def delete_follow_up(follow_up_id: int) -> dict:
    """删跟进；``attachments`` 行由外键级联清掉，磁盘文件留给备份清理。"""
    with db_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM follow_ups WHERE id = ?", (follow_up_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="跟进记录不存在")
        conn.execute("DELETE FROM follow_ups WHERE id = ?", (follow_up_id,))

    return {"ok": True, "id": follow_up_id}
