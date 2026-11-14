"""版本化外部 API：按手机号新增客户或线索跟进。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.db import db_conn
from app.external_auth import ExternalTokenContext, require_external_token
from app.followup_service import (
    clean_content,
    clean_next_date,
    create_follow_up_record,
    prepare_attachments,
    resolve_followup_target_by_phone,
)
from app.models import FollowUpItemOut

router = APIRouter(prefix="/api/external/v1", tags=["external"])


@router.post(
    "/follow-ups",
    response_model=FollowUpItemOut,
    status_code=201,
)
async def create_external_follow_up(
    phone: str = Form(...),
    content: str = Form(...),
    method: str | None = Form(default=None),
    next_date: str | None = Form(default=None),
    attachments: list[UploadFile] = File(
        default=[],
        description="重复字段；最多 10 个，单个不超过 20MB",
    ),
    token: ExternalTokenContext = Depends(require_external_token),
) -> FollowUpItemOut:
    content_value = clean_content(content)
    next_date_value = clean_next_date(next_date)
    prepared = await prepare_attachments(attachments)

    with db_conn() as conn:
        object_type, object_id = resolve_followup_target_by_phone(conn, phone)
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
