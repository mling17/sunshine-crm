"""外部写接口的 Idempotency-Key 存储与响应回放。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.db import IntegrityError
from app.errors import ApiError
from app.security import now_iso, to_iso, utc_now

LEADS_ENDPOINT = "POST /api/external/v1/leads"
FOLLOW_UPS_ENDPOINT = "POST /api/external/v1/follow-ups"
RETENTION_DAYS = 30
MAX_KEY_LENGTH = 255


@dataclass(frozen=True)
class IdempotencyIdentity:
    token_id: int
    endpoint: str
    key: str
    request_hash: str
    expires_at: str


class IdempotencyRace(Exception):
    """同一唯一键被并发请求先占用。"""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def request_fingerprint(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def attachment_fingerprint(file_name: str, mime_type: str, data: bytes) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "mime_type": mime_type,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def identity_from_request(
    request: Request,
    *,
    token_id: int,
    endpoint: str,
    request_payload: Any,
) -> IdempotencyIdentity | None:
    raw_key = request.headers.get("idempotency-key")
    if raw_key is None:
        return None
    key = raw_key.strip()
    if not key:
        raise ApiError(400, "invalid_idempotency_key", "Idempotency-Key 不能为空")
    if len(key) > MAX_KEY_LENGTH:
        raise ApiError(
            400,
            "invalid_idempotency_key",
            f"Idempotency-Key 最多 {MAX_KEY_LENGTH} 个字符",
        )
    return IdempotencyIdentity(
        token_id=token_id,
        endpoint=endpoint,
        key=key,
        request_hash=request_fingerprint(request_payload),
        expires_at=to_iso(utc_now() + timedelta(days=RETENTION_DAYS)),
    )


def cleanup_expired(conn, now: str | None = None) -> int:
    """物理清理过期缓存行；幂等缓存不是业务主数据。"""
    cursor = conn.execute(
        "DELETE FROM api_idempotency_records WHERE expires_at <= ?",
        (now or now_iso(),),
    )
    return int(cursor.rowcount or 0)


def _replay_response(row) -> JSONResponse:
    return JSONResponse(
        content=json.loads(row["response_body"]),
        status_code=int(row["response_status"]),
    )


def claim(conn, identity: IdempotencyIdentity) -> JSONResponse | None:
    """占用键或返回已保存响应；不同请求 hash 返回稳定冲突。"""
    cleanup_expired(conn)
    row = conn.execute(
        """
        SELECT id, request_hash, response_status, response_body
        FROM api_idempotency_records
        WHERE token_id = ? AND endpoint = ? AND idempotency_key = ?
          AND is_delete = 0
        """,
        (identity.token_id, identity.endpoint, identity.key),
    ).fetchone()
    if row is not None:
        if row["request_hash"] != identity.request_hash:
            raise ApiError(
                409,
                "idempotency_conflict",
                "同一 Idempotency-Key 不能用于不同请求",
            )
        if row["response_body"] is None:
            raise ApiError(
                409,
                "idempotency_in_progress",
                "同一 Idempotency-Key 的请求正在处理中",
            )
        return _replay_response(row)

    now = now_iso()
    try:
        conn.execute(
            """
            INSERT INTO api_idempotency_records
                (token_id, endpoint, idempotency_key, request_hash,
                 response_status, response_body, expires_at,
                 created_at, updated_at, create_time, update_time)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
            """,
            (
                identity.token_id,
                identity.endpoint,
                identity.key,
                identity.request_hash,
                identity.expires_at,
                now,
                now,
                now,
                now,
            ),
        )
    except IntegrityError as exc:
        raise IdempotencyRace() from exc
    return None


def replay_after_race(conn, identity: IdempotencyIdentity) -> JSONResponse:
    row = conn.execute(
        """
        SELECT request_hash, response_status, response_body
        FROM api_idempotency_records
        WHERE token_id = ? AND endpoint = ? AND idempotency_key = ?
          AND is_delete = 0
        """,
        (identity.token_id, identity.endpoint, identity.key),
    ).fetchone()
    if row is None:
        raise ApiError(
            409,
            "idempotency_in_progress",
            "同一 Idempotency-Key 的请求正在处理中",
        )
    if row["request_hash"] != identity.request_hash:
        raise ApiError(
            409,
            "idempotency_conflict",
            "同一 Idempotency-Key 不能用于不同请求",
        )
    if row["response_body"] is None:
        raise ApiError(
            409,
            "idempotency_in_progress",
            "同一 Idempotency-Key 的请求正在处理中",
        )
    return _replay_response(row)


def complete(
    conn,
    identity: IdempotencyIdentity,
    *,
    status_code: int,
    response_payload: Any,
) -> JSONResponse:
    body = _canonical_json(response_payload)
    cursor = conn.execute(
        """
        UPDATE api_idempotency_records
        SET response_status = ?, response_body = ?, updated_at = ?, update_time = ?
        WHERE token_id = ? AND endpoint = ? AND idempotency_key = ?
          AND request_hash = ? AND is_delete = 0
        """,
        (
            status_code,
            body,
            now_iso(),
            now_iso(),
            identity.token_id,
            identity.endpoint,
            identity.key,
            identity.request_hash,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        raise ApiError(
            500,
            "idempotency_state_error",
            "Idempotency-Key 状态写入失败",
        )
    return JSONResponse(
        content=json.loads(body),
        status_code=status_code,
    )
