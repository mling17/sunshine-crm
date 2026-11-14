"""版本化外部 API：使用长期 Bearer Token 新增线索。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.db import db_conn
from app.errors import ApiError
from app.external_auth import ExternalTokenContext, require_external_token
from app.idempotency import (
    LEADS_ENDPOINT,
    IdempotencyRace,
    claim,
    complete,
    identity_from_request,
    replay_after_race,
)
from app.lead_service import active_lead_phone_keys, create_lead_record, fetch_lead
from app.models import (
    ExternalLeadIn,
    ExternalPhoneCheckIn,
    ExternalPhoneCheckItem,
    ExternalPhoneCheckOut,
    LeadOut,
)
from app.phone import canonicalize_mainland_mobile

router = APIRouter(prefix="/api/external/v1", tags=["external"])


def _lead_fingerprint(payload: ExternalLeadIn, phone: str) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    data["phone"] = phone
    data["source"] = "api"
    data["status"] = "new"
    data["lead_type"] = payload.lead_type or "other"
    seen: set[str] = set()
    tags: list[str] = []
    for raw in payload.tags:
        name = raw.strip()
        if name and name not in seen:
            seen.add(name)
            tags.append(name)
    data["tags"] = tags
    return data


def _create_lead(
    conn,
    payload: ExternalLeadIn,
    phone: str,
    token: ExternalTokenContext,
) -> LeadOut:
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


@router.post("/leads", response_model=LeadOut, status_code=201)
def create_external_lead(
    payload: ExternalLeadIn,
    request: Request,
    token: ExternalTokenContext = Depends(require_external_token),
) -> LeadOut | JSONResponse:
    try:
        phone = canonicalize_mainland_mobile(payload.phone)
    except ValueError:
        raise ApiError(400, "invalid_phone", "手机号格式不正确") from None

    identity = identity_from_request(
        request,
        token_id=token.token_id,
        endpoint=LEADS_ENDPOINT,
        request_payload=_lead_fingerprint(payload, phone),
    )
    if identity is None:
        with db_conn() as conn:
            return _create_lead(conn, payload, phone, token)

    try:
        with db_conn() as conn:
            replay = claim(conn, identity)
            if replay is not None:
                return replay
            lead = _create_lead(conn, payload, phone, token)
            return complete(
                conn,
                identity,
                status_code=201,
                response_payload=lead.model_dump(mode="json"),
            )
    except IdempotencyRace:
        with db_conn() as conn:
            return replay_after_race(conn, identity)


@router.post("/leads/phone-check", response_model=ExternalPhoneCheckOut)
def check_external_lead_phones(
    payload: ExternalPhoneCheckIn,
    _: ExternalTokenContext = Depends(require_external_token),
) -> ExternalPhoneCheckOut:
    canonical: list[str] = []
    seen: set[str] = set()
    invalid_positions: list[int] = []
    for position, raw in enumerate(payload.phones):
        try:
            phone = canonicalize_mainland_mobile(raw)
        except ValueError:
            invalid_positions.append(position)
            continue
        if phone not in seen:
            seen.add(phone)
            canonical.append(phone)

    if invalid_positions:
        raise ApiError(
            400,
            "invalid_phone",
            "手机号格式不正确",
            invalid_positions=invalid_positions,
        )

    with db_conn() as conn:
        existing = active_lead_phone_keys(conn, canonical)

    return ExternalPhoneCheckOut(
        items=[
            ExternalPhoneCheckItem(phone=phone, exists=phone in existing)
            for phone in canonical
        ]
    )
