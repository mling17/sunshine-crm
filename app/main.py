"""天窗天幕 CRM · FastAPI 入口。

启动时（lifespan）做的事：
1. 建表建索引（幂等）；
2. 运行迁移（幂等）；
3. 建上传目录；
4. ``users`` 表为空时，按 ``ADMIN_USERNAME/ADMIN_PASSWORD`` 种一个 PBKDF2 用户。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.db import db_conn
from app.routers import (
    stats,
    addresses,
    aftersales,
    attachments,
    auth,
    carriers,
    csvimport,
    customers,
    dashboard,
    deals,
    dicts,
    external_followups,
    external_leads,
    followups,
    leads,
    orders,
    products,
    quotes,
)
from app.schema import ensure_schema
from app.migrations import run_migrations
from app.deal_tags import backfill_pending_quote_tags
from app.errors import install_error_handler
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
    ensure_schema(None if settings.CRM_DB_ENGINE == "mysql" else settings.db_path)
    if settings.CRM_DB_ENGINE == "mysql":
        from app.mysql_schema import mysql_runtime_seed

        with db_conn() as conn:
            mysql_runtime_seed(conn)
            backfill_pending_quote_tags(conn)
    else:
        run_migrations(settings.db_path)  # V2 增量迁移
        with db_conn() as conn:
            backfill_pending_quote_tags(conn)
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    seed_admin_if_needed()
    log.info(
        "CRM 启动完成：db=%s engine=%s uploads=%s session_ttl=%sh",
        settings.database_label,
        settings.CRM_DB_ENGINE,
        settings.uploads_path,
        settings.SESSION_TTL_HOURS,
    )
    yield


app = FastAPI(title="天窗天幕 CRM", version="1.0.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.middleware("http")
async def serve_existing_crm_api_prefix(request: Request, call_next):
    """兼容前端固定的 ``/crm/api/...`` 路径。

    原部署由 nginx 去掉 ``/crm`` 前缀；独立容器没有 nginx，因此在 ASGI
    路由前完成同一层重写，保证页面和 API 可由同一个镜像直接提供。
    """
    path = request.scope.get("path", "")
    if path == "/crm/api" or path.startswith("/crm/api/"):
        request.scope["path"] = path.removeprefix("/crm")
        raw_path = request.scope.get("raw_path")
        if raw_path:
            request.scope["raw_path"] = raw_path.removeprefix(b"/crm")
    return await call_next(request)

# 与 learning_kb 保持一致（只为直连 8011 调试方便；生产走 nginx 同源代理）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册错误处理器
install_error_handler(app)

@app.get("/health", tags=["meta"])
def health() -> dict:
    """探活接口：不鉴权，给 systemd / nginx / 监控用。"""
    return {
        "status": "ok",
        "db": settings.database_label,
        "db_engine": settings.CRM_DB_ENGINE,
        "ts": now_iso(),
    }


app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(deals.router)
app.include_router(followups.router)
app.include_router(attachments.router)
app.include_router(dashboard.router)
app.include_router(csvimport.router)
app.include_router(leads.router)
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(quotes.router)
app.include_router(carriers.router)
app.include_router(aftersales.router)
app.include_router(addresses.router)
app.include_router(stats.router)
app.include_router(dicts.router)
app.include_router(external_leads.router)
app.include_router(external_followups.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/crm/")


# 独立容器可直接访问 http://host:8010/crm/；nginx 部署仍可继续由 nginx
# 提供静态文件，这里不会改变 /api/crm 接口。
app.mount("/crm", StaticFiles(directory=STATIC_DIR, html=True), name="crm")
