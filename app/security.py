"""密码校验（零依赖：只用 stdlib）。

存储格式：``$pbkdf2$<iters>$<salt_hex>$<hash_hex>``
- 算法：PBKDF2-HMAC-SHA256
- 迭代：200000（本机没有 bcrypt，这是项目已拍板的方案）

会话 token / 过期时间的工具在 T2 加进来（同一个模块，认证域的东西放一起）。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.config.settings import settings

PBKDF2_ITERATIONS = 200_000
_HASH_ALGO = "sha256"
_SALT_BYTES = 16


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """生成 ``$pbkdf2$200000$<salt>$<hash>``。每次调用都用新的随机盐。"""
    if not password:
        raise ValueError("password 不能为空")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(_HASH_ALGO, password.encode("utf-8"), salt, iterations)
    return f"$pbkdf2${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码；任何格式异常都返回 False（不抛异常，避免登录接口 500）。"""
    if not isinstance(stored, str):
        return False
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")[1:]
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            _HASH_ALGO,
            (password or "").encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    # 定长比较，避免时序侧信道
    return secrets.compare_digest(digest.hex(), hash_hex)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    """统一成 ``2026-10-29T09:00:00Z``；固定格式才能用字符串比较时间先后。"""
    return (
        dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def now_iso() -> str:
    return to_iso(utc_now())


# ------------------------- 会话 -------------------------


def new_session_token() -> str:
    """会话 token：32 字节随机数 = 64 位 hex，不可猜。"""
    return secrets.token_hex(32)


def session_expires_at(now: datetime | None = None) -> datetime:
    """固定 12h（settings.SESSION_TTL_HOURS），不随请求滑动 → 每天重登一次。"""
    return (now or utc_now()) + timedelta(hours=settings.SESSION_TTL_HOURS)


def now_local_iso() -> str:
    """服务器本地时间 ``YYYY-MM-DDTHH:MM:SS``（**刻意不带 Z、不带时区偏移**）。

    ``deals.closed_at`` 用它：T6 的「本月成交」按
    ``strftime('%Y-%m', closed_at)`` 与 ``'now','localtime'`` 比较，
    带 +08:00 偏移的字符串会被 SQLite 先转成 UTC，跨月零点就会算错月份。
    """
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
