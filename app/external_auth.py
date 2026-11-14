"""外部 API 的长期 Bearer Token 鉴权。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.db import db_conn
from app.errors import ApiError
from app.security import now_iso


@dataclass(frozen=True)
class ExternalTokenContext:
    token_id: int
    user_id: int
    username: str


def _unauthorized() -> ApiError:
    return ApiError(401, "unauthorized", "认证失败")


def require_external_token(request: Request) -> ExternalTokenContext:
    """只接受 ``Authorization: Bearer <token>``，所有失败形态返回同一 401。"""
    raw = (request.headers.get("authorization") or "").strip()
    parts = raw.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise _unauthorized()

    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.user_id, u.username
            FROM api_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token = ?
              AND t.is_delete = 0
              AND u.is_delete = 0
              AND u.is_active = 1
              AND t.revoked_at IS NULL
              AND (t.expires_at IS NULL OR t.expires_at = '' OR t.expires_at > ?)
            """,
            (parts[1], now_iso()),
        ).fetchone()
    if row is None:
        raise _unauthorized()
    return ExternalTokenContext(
        token_id=int(row["id"]),
        user_id=int(row["user_id"]),
        username=str(row["username"]),
    )
