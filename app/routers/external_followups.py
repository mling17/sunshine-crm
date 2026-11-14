"""版本化外部 API：按手机号新增客户或线索跟进。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.db import db_conn
from app.errors import ApiError
from app.external_auth import ExternalTokenContext, require_external_token
from app.followup_service import (
    clean_content,
    clean_next_date,
    create_follow_up_record,
    prepare_attachments,
    resolve_followup_target_by_phone,
)
from app.idempotency import (
    FOLLOW_UPS_ENDPOINT,
    IdempotencyRace,
    attachment_fingerprint,
    claim,
    complete,
    identity_from_request,
    replay_after_race,
)
from app.models import FollowUpItemOut
from app.phone import canonicalize_mainland_mobile

router = APIRouter(prefix="/api/external/v1", tags=["external"])


@router.post(
    "/follow-ups",
    response_model=FollowUpItemOut,
    status_code=201,
)
async def create_external_follow_up(
    request: Request,
    phone: str = Form(...),
    content: str = Form(...),
    method: str | None = Form(default=None),
    next_date: str | None = Form(default=None),
    attachments: list[UploadFile] = File(
        default=[],
        description="重复字段；最多 10 个，单个不超过 20MB",
    ),
    token: ExternalTokenContext = Depends(require_external_token),
) -> FollowUpItemOut | JSONResponse:
    content_value = clean_content(content)
    next_date_value = clean_next_date(next_date)
    prepared = await prepare_attachments(attachments)
    try:
        phone_value = canonicalize_mainland_mobile(phone)
    except ValueError:
        raise ApiError(400, "invalid_phone", "手机号格式不正确") from None

    identity = identity_from_request(
        request,
        token_id=token.token_id,
        endpoint=FOLLOW_UPS_ENDPOINT,
        request_payload={
            "phone": phone_value,
            "content": content_value,
            "method": (method or "").strip(),
            "next_date": next_date_value,
            "attachments": [
                attachment_fingerprint(
                    item.file_name,
                    item.mime_type,
                    item.data,
                )
                for item in prepared
            ],
        },
    )

    def create(conn) -> FollowUpItemOut:
        object_type, object_id = resolve_followup_target_by_phone(conn, phone_value)
        return create_follow_up_record(
            conn,
            object_type=object_type,
            object_id=object_id,
            content=content_value,
            method=method,
            next_date=next_date_value,
            attachments=prepared,
            created_by=token.user_id,
        )

    if identity is None:
        with db_conn() as conn:
            return create(conn)

    try:
        with db_conn() as conn:
            replay = claim(conn, identity)
            if replay is not None:
                return replay
            completed_response: JSONResponse | None = None

            def finish(item: FollowUpItemOut) -> None:
                nonlocal completed_response
                completed_response = complete(
                    conn,
                    identity,
                    status_code=201,
                    response_payload=item.model_dump(mode="json"),
                )

            object_type, object_id = resolve_followup_target_by_phone(
                conn, phone_value
            )
            create_follow_up_record(
                conn,
                object_type=object_type,
                object_id=object_id,
                content=content_value,
                method=method,
                next_date=next_date_value,
                attachments=prepared,
                created_by=token.user_id,
                # 在共享写入函数内完成幂等响应：若最终状态写入失败，
                # 仍由同一异常路径回滚数据库并删除本次已写文件。
                completion=finish,
            )
            if completed_response is None:
                raise ApiError(
                    500,
                    "idempotency_state_error",
                    "Idempotency-Key 状态写入失败",
                )
            return completed_response
    except IdempotencyRace:
        with db_conn() as conn:
            return replay_after_race(conn, identity)
