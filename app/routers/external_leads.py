"""版本化外部 API：使用长期 Bearer Token 新增线索。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import db_conn
from app.errors import ApiError
from app.external_auth import ExternalTokenContext, require_external_token
from app.lead_service import create_lead_record, fetch_lead
from app.models import ExternalLeadIn, LeadOut
from app.phone import canonicalize_mainland_mobile

router = APIRouter(prefix="/api/external/v1", tags=["external"])


@router.post("/leads", response_model=LeadOut, status_code=201)
def create_external_lead(
    payload: ExternalLeadIn,
    token: ExternalTokenContext = Depends(require_external_token),
) -> LeadOut:
    try:
        phone = canonicalize_mainland_mobile(payload.phone)
    except ValueError:
        raise ApiError(400, "invalid_phone", "手机号格式不正确") from None

    with db_conn() as conn:
        lead_id = create_lead_record(
            conn,
            name=payload.name,
            phone=phone,
            wechat=payload.wechat,
            lead_type=payload.lead_type or "other",
            company_name=payload.company_name,
            source="api",
            source_other=payload.source_other,
            location=payload.location,
            note=payload.note,
            intent_level=payload.intent_level,
            owner=payload.owner,
            tags=payload.tags,
            created_by=token.user_id,
        )
        return fetch_lead(conn, lead_id)
