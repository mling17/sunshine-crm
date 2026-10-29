"""天窗天幕 CRM · FastAPI 入口。

启动时（lifespan）做的事：
1. 建表建索引（幂等）；
2. 建上传目录；
3. ``users`` 表为空时，按 ``ADMIN_USERNAME/ADMIN_PASSWORD`` 种一个 PBKDF2 用户。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.db import db_conn
from app.routers import attachments, auth, customers, dashboard, deals, followups
from app.schema import ensure_schema
from app.security import hash_password, now_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("crm")


def seed_admin_if_needed() -> None:
    """users 为空才种账号；已有账号时 env 里的密码不会覆盖 DB（避免误改线上密码）。"""
    with db_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count:
            return
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (
                settings.ADMIN_USERNAME,
                hash_password(settings.ADMIN_PASSWORD),
                now_iso(),
            ),
        )
    log.warning(
        "users 表为空，已创建种子账号 %r（密码来自 ADMIN_PASSWORD，请尽快更换）",
        settings.ADMIN_USERNAME,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema(settings.db_path)
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    seed_admin_if_needed()
    log.info(
        "CRM 启动完成：db=%s uploads=%s session_ttl=%sh",
        settings.db_path,
        settings.uploads_path,
        settings.SESSION_TTL_HOURS,
    )
    yield


app = FastAPI(title="天窗天幕 CRM", version="1.0.0", lifespan=lifespan)

# 与 learning_kb 保持一致（只为直连 8011 调试方便；生产走 nginx 同源代理）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """探活接口：不鉴权，给 systemd / nginx / 监控用。"""
    return {"status": "ok", "db": str(settings.db_path), "ts": now_iso()}


app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(deals.router)
app.include_router(followups.router)
app.include_router(attachments.router)
app.include_router(dashboard.router)
