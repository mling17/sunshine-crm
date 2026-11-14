"""跟进创建的共享校验、持久化与附件原子性服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fastapi import HTTPException, UploadFile

from app import labels
from app.errors import ApiError
from app.models import AttachmentOut, FollowUpItemOut
from app.phone import canonicalize_mainland_mobile
from app.security import now_iso, now_local_iso
from app.storage import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_FOLLOWUP,
    ext_and_mime_any,
    new_storage_key,
    resolve_upload_path,
    save_photo,
)
from app.timeline import add_entry


@dataclass(frozen=True)
class PreparedAttachment:
    file_name: str
    mime_type: str
    extension: str
    data: bytes


def clean_content(raw: str | None) -> str:
    content = (raw or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="跟进内容不能为空")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="跟进内容最多 2000 字")
    return content


def clean_next_date(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="next_date 格式必须是 YYYY-MM-DD",
        ) from None
    return parsed.strftime("%Y-%m-%d")


async def prepare_attachments(
    uploads: list[UploadFile] | None,
) -> list[PreparedAttachment]:
    """读完并校验全部附件后才允许调用持久化。"""
    prepared: list[PreparedAttachment] = []
    for upload in uploads or []:
        data = await upload.read()
        filename = (upload.filename or "").strip()
        if not filename and not data:
            continue
        if not data:
            raise HTTPException(status_code=400, detail=f"附件 {filename} 是空文件")
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"附件 {filename} 超过 {MAX_FILE_BYTES // (1024 * 1024)}MB",
            )
        extension, mime_type = ext_and_mime_any(filename)
        prepared.append(
            PreparedAttachment(
                file_name=filename or f"file{extension}",
                mime_type=mime_type,
                extension=extension,
                data=data,
            )
        )
    if len(prepared) > MAX_FILES_PER_FOLLOWUP:
        raise HTTPException(
            status_code=400,
            detail=(
                f"一条跟进最多 {MAX_FILES_PER_FOLLOWUP} 个附件，"
                f"本次选了 {len(prepared)} 个"
            ),
        )
    return prepared


def _canonical_phone(raw: object) -> str:
    try:
        return canonicalize_mainland_mobile(raw)
    except ValueError:
        return ""


def resolve_followup_target_by_phone(conn, phone: str) -> tuple[str, int]:
    """客户优先，其次线索；返回唯一的有效目标。"""
    try:
        canonical = canonicalize_mainland_mobile(phone)
    except ValueError:
        raise ApiError(400, "invalid_phone", "手机号格式不正确") from None

    for object_type, table, has_status in (
        ("customer", "customers", False),
        ("lead", "leads", True),
    ):
        status_sql = ", status" if has_status else ""
        rows = conn.execute(
            f"SELECT id, phone{status_sql} FROM {table}"
            " WHERE is_delete = 0 AND phone IS NOT NULL"
        ).fetchall()
        matches = [
            row for row in rows if _canonical_phone(row["phone"]) == canonical
        ]
        if len(matches) > 1:
            raise ApiError(
                status_code=409,
                code="ambiguous_phone",
                message=f"{canonical}对应多条{object_type}记录",
            )
        if not matches:
            continue
        row = matches[0]
        if has_status and row["status"] in ("converted", "invalid"):
            raise ApiError(
                status_code=409,
                code="lead_closed",
                message="线索已转化或已无效，无法添加跟进",
            )
        return object_type, int(row["id"])

    raise ApiError(
        status_code=404,
        code="phone_not_found",
        message=f"{canonical}手机号不存在",
    )


def _validate_object_type(object_type: str) -> None:
    if object_type not in ("lead", "customer", "deal", "order", "aftersale"):
        raise HTTPException(status_code=400, detail=f"非法对象类型 {object_type!r}")


def _validate_quote(
    conn,
    *,
    object_type: str,
    object_id: int,
    quote_id: int | None,
    deal_id_hint: int | None,
) -> None:
    if quote_id is None:
        return
    quote = conn.execute(
        "SELECT deal_id, status FROM deal_quotes WHERE id = ? AND is_delete = 0",
        (quote_id,),
    ).fetchone()
    if quote is None:
        raise HTTPException(status_code=404, detail="报价单不存在")
    if quote["status"] == "void":
        raise ApiError(
            status_code=409,
            code="quote_history_locked",
            message="历史报价单不能添加关联跟进",
        )
    expected_deal_id = deal_id_hint or (
        object_id if object_type == "deal" else None
    )
    if expected_deal_id is None or int(quote["deal_id"]) != expected_deal_id:
        raise HTTPException(status_code=400, detail="报价单不属于当前商机")


def _validate_target(
    conn,
    *,
    object_type: str,
    object_id: int,
    customer_id_hint: int | None,
    deal_id_hint: int | None,
) -> None:
    _validate_object_type(object_type)

    if customer_id_hint and deal_id_hint:
        deal = conn.execute(
            "SELECT customer_id FROM deals WHERE id = ? AND is_delete = 0",
            (deal_id_hint,),
        ).fetchone()
        if deal is None:
            raise HTTPException(status_code=404, detail="商机不存在")
        if int(deal["customer_id"]) != customer_id_hint:
            raise HTTPException(status_code=400, detail="商机不属于该客户")

    if deal_id_hint:
        deal = conn.execute(
            "SELECT customer_id FROM deals WHERE id = ? AND is_delete = 0",
            (deal_id_hint,),
        ).fetchone()
        if deal is None:
            raise HTTPException(status_code=404, detail="商机不存在")
        if object_type == "customer" and int(deal["customer_id"]) != object_id:
            raise HTTPException(status_code=400, detail="商机不属于该客户")

    if object_type == "lead":
        lead = conn.execute(
            "SELECT status FROM leads WHERE id = ? AND is_delete = 0",
            (object_id,),
        ).fetchone()
        if lead is None:
            raise HTTPException(status_code=404, detail="线索不存在")
        if lead["status"] in ("converted", "invalid"):
            raise ApiError(
                status_code=409,
                code="lead_closed",
                message="线索已转化或已无效，无法添加跟进",
            )
    elif object_type == "customer":
        customer = conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND is_delete = 0",
            (object_id,),
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="客户不存在")
    elif object_type == "deal":
        deal = conn.execute(
            "SELECT stage, order_id FROM deals WHERE id = ? AND is_delete = 0",
            (object_id,),
        ).fetchone()
        if deal is None:
            raise HTTPException(status_code=404, detail="商机不存在")
        if deal["order_id"] is not None or deal["stage"] == "lost":
            raise ApiError(
                status_code=409,
                code="deal_frozen",
                message="商机已赢单或已流失，无法添加跟进",
            )
    elif object_type == "order":
        order = conn.execute(
            "SELECT status FROM orders WHERE id = ? AND is_delete = 0",
            (object_id,),
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
        aftersale = conn.execute(
            "SELECT status FROM aftersales WHERE id = ? AND is_delete = 0",
            (object_id,),
        ).fetchone()
        if aftersale is None:
            raise HTTPException(status_code=404, detail="售后单不存在")
        if aftersale["status"] == "done":
            raise ApiError(
                status_code=409,
                code="aftersale_closed",
                message="该售后单已完成，不能再添加跟进记录",
            )


def _apply_stage(conn, deal_id: int, old_stage: str, new_stage: str) -> None:
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


def _cleanup_written_files(keys: list[str]) -> None:
    for key in keys:
        try:
            resolve_upload_path(key, must_exist=False).unlink(missing_ok=True)
        except OSError:
            pass


def create_follow_up_record(
    conn,
    *,
    object_type: str,
    object_id: int,
    content: str,
    method: str | None,
    next_date: str | None,
    attachments: list[PreparedAttachment],
    created_by: int,
    intent_level: str | None = None,
    stage: str | None = None,
    quote_id: int | None = None,
    customer_id_hint: int | None = None,
    deal_id_hint: int | None = None,
    completion: Callable[[FollowUpItemOut], None] | None = None,
) -> FollowUpItemOut:
    """在调用方事务内写跟进、附件和业务状态；失败时清理本次文件。"""
    content_value = clean_content(content)
    next_date_value = clean_next_date(next_date)
    method_value = (method or "").strip()
    intent_value = (intent_level or "").strip()
    _validate_target(
        conn,
        object_type=object_type,
        object_id=object_id,
        customer_id_hint=customer_id_hint,
        deal_id_hint=deal_id_hint,
    )
    _validate_quote(
        conn,
        object_type=object_type,
        object_id=object_id,
        quote_id=quote_id,
        deal_id_hint=deal_id_hint,
    )

    written_keys: list[str] = []
    created_at = now_iso()
    try:
        customer_id_value: int | None = None
        deal_id_value: int | None = None
        if deal_id_hint and object_type != "deal":
            deal_id_value = deal_id_hint
        if object_type == "customer":
            customer_id_value = object_id
        elif object_type == "deal":
            deal = conn.execute(
                "SELECT customer_id FROM deals WHERE id = ? AND is_delete = 0",
                (object_id,),
            ).fetchone()
            customer_id_value = int(deal["customer_id"])
            deal_id_value = object_id
        elif object_type == "order":
            order = conn.execute(
                "SELECT customer_id FROM orders WHERE id = ? AND is_delete = 0",
                (object_id,),
            ).fetchone()
            customer_id_value = int(order["customer_id"])
        elif object_type == "aftersale":
            aftersale = conn.execute(
                "SELECT customer_id FROM aftersales WHERE id = ? AND is_delete = 0",
                (object_id,),
            ).fetchone()
            customer_id_value = int(aftersale["customer_id"])

        cur = conn.execute(
            """
            INSERT INTO follow_ups
                (object_type, object_id, customer_id, deal_id, quote_id, method,
                 kind, content, next_date, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'follow', ?, ?, ?, ?)
            """,
            (
                object_type,
                object_id,
                customer_id_value,
                deal_id_value,
                quote_id,
                method_value,
                content_value,
                next_date_value,
                created_by,
                created_at,
            ),
        )
        follow_up_id = int(cur.lastrowid or 0)

        if object_type == "lead":
            current = conn.execute(
                "SELECT status FROM leads WHERE id = ? AND is_delete = 0",
                (object_id,),
            ).fetchone()
            if current["status"] == "new":
                conn.execute(
                    "UPDATE leads SET status = 'following', updated_at = ? WHERE id = ?",
                    (created_at, object_id),
                )
                add_entry(
                    conn,
                    object_type="lead",
                    object_id=object_id,
                    kind="change",
                    content="状态更新：新线索 → 跟进中",
                )
            else:
                conn.execute(
                    "UPDATE leads SET updated_at = ? WHERE id = ?",
                    (created_at, object_id),
                )

        if object_type == "aftersale":
            current = conn.execute(
                "SELECT status FROM aftersales WHERE id = ? AND is_delete = 0",
                (object_id,),
            ).fetchone()
            if current["status"] == "pending":
                conn.execute(
                    "UPDATE aftersales SET status = 'processing', updated_at = ? WHERE id = ?",
                    (created_at, object_id),
                )
                conn.execute(
                    "INSERT INTO aftersale_status_log"
                    " (aftersale_id, from_status, to_status, note, created_at)"
                    " VALUES (?, 'pending', 'processing', ?, ?)",
                    (object_id, "记跟进后自动进入处理中", created_at),
                )
                add_entry(
                    conn,
                    object_type="aftersale",
                    object_id=object_id,
                    kind="stage",
                    content="状态变更：待处理 → 处理中",
                    detail={"from": "pending", "to": "processing"},
                )

        for attachment in attachments:
            storage_key = new_storage_key(attachment.extension)
            written_keys.append(storage_key)
            save_photo(storage_key, attachment.data)
            conn.execute(
                """
                INSERT INTO attachments
                    (object_type, object_id, follow_up_id, storage_key, file_name,
                     mime_type, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_type,
                    object_id,
                    follow_up_id,
                    storage_key,
                    attachment.file_name,
                    attachment.mime_type,
                    len(attachment.data),
                    created_at,
                ),
            )

        if intent_value and object_type in ("lead", "customer"):
            table = "leads" if object_type == "lead" else "customers"
            conn.execute(
                f"UPDATE {table} SET intent_level = ?, updated_at = ? WHERE id = ?",
                (intent_value, created_at, object_id),
            )

        if stage and deal_id_value is not None:
            deal = conn.execute(
                "SELECT stage FROM deals WHERE id = ? AND is_delete = 0",
                (deal_id_value,),
            ).fetchone()
            old_stage = deal["stage"] if deal else ""
            _apply_stage(conn, deal_id_value, old_stage, stage)

        item = fetch_follow_up_item(conn, follow_up_id)
        if completion is not None:
            completion(item)
        return item
    except BaseException:
        try:
            conn.rollback()
        finally:
            _cleanup_written_files(written_keys)
        raise


def photos_for(conn, follow_up_ids: list[int]) -> dict[int, list[AttachmentOut]]:
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
                **dict(row),
                url=f"/api/crm/attachments/{row['id']}",
            )
        )
    return grouped


def follow_up_to_item(row, photos: list[AttachmentOut]) -> FollowUpItemOut:
    data = dict(row)
    raw_detail = data.get("detail")
    if isinstance(raw_detail, str) and raw_detail:
        try:
            data["detail"] = json.loads(raw_detail)
        except (TypeError, ValueError):
            data["detail"] = None
    data["method_label"] = labels.follow_method(data.get("method"))
    return FollowUpItemOut(**data, photo_count=len(photos), photos=photos)


def fetch_follow_up_item(conn, follow_up_id: int) -> FollowUpItemOut:
    row = conn.execute(
        """
        SELECT fu.id, fu.customer_id, fu.deal_id, fu.quote_id, fu.object_type,
               fu.object_id, fu.method, fu.kind, fu.content, fu.detail,
               fu.next_date, fu.created_by, fu.created_at,
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
    return follow_up_to_item(
        row,
        photos_for(conn, [follow_up_id]).get(follow_up_id, []),
    )
