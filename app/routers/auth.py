"""认证路由：登录 / 登出 / 当前用户 + ``require_auth`` 依赖。

会话模型（已拍板）：
- 登录成功写一行 ``sessions``（token = secrets.token_hex(32)）；
- Cookie 名 ``crm_sid``，HttpOnly + SameSite=Lax + Path=/ + Max-Age=43200（12h，固定不滑动）；
- 除 ``/health``、``/api/crm/login`` 外，所有数据路由挂 ``Depends(require_auth)``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.db import db_conn
from app.security import (
    new_session_token,
    now_iso,
    session_expires_at,
    to_iso,
    verify_password,
)

router = APIRouter(prefix="/api/crm", tags=["auth"])

COOKIE_NAME = settings.COOKIE_NAME
# Max-Age 用秒；与 settings.SESSION_TTL_HOURS 保持单一来源
COOKIE_MAX_AGE = settings.SESSION_TTL_HOURS * 3600


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _unauthorized(detail: str = "未登录或会话已过期") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def require_auth(request: Request) -> str:
    """校验 Cookie 里的会话；通过则返回用户名，否则 401。

    过期判定交给 SQL 比较（``expires_at > now``），过期行留在库里也无害
    —— 登录时会顺手清理（见 login）。
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized()

    with db_conn() as conn:
        row = conn.execute(
            "SELECT username FROM sessions WHERE token = ? AND expires_at > ?",
            (token, now_iso()),
        ).fetchone()

    if row is None:
        raise _unauthorized()
    return row["username"]


@router.post("/login")
def login(payload: LoginIn, response: Response) -> dict:
    with db_conn() as conn:
        user = conn.execute(
            "SELECT username, password_hash FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()

        # 账号不存在与密码错误返回同一句话，不泄露哪个错了
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise _unauthorized("账号或密码错误")

        created_at = now_iso()
        expires_at = session_expires_at()
        token = new_session_token()

        # 顺手清掉过期会话，避免 sessions 表无限增长
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (created_at,))
        conn.execute(
            "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user["username"], created_at, to_iso(expires_at)),
        )

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,          # JS 读不到，防 XSS 偷 token
        samesite="lax",         # 跨站 POST 不带 cookie，防 CSRF 的基线
        path="/",
        secure=settings.COOKIE_SECURE,  # 内网 HTTP 阶段为 False，上 HTTPS 后置 1
    )
    return {"username": user["username"], "expires_at": to_iso(expires_at)}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    """登出：删会话行 + 清 Cookie。不要求已登录（幂等，避免过期后点登出 401）。"""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with db_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(username: str = Depends(require_auth)) -> dict:
    return {"username": username}
