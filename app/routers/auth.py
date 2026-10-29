"""认证路由。

T1 只建立路由骨架（保证 main.py 能挂载 router），登录 / 登出 / me 在 T2 实现。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/crm", tags=["auth"])
