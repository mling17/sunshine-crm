"""附件读取：``GET /api/crm/attachments/{id}`` 流式返回图片。

安全（T5 的硬要求）：
- 必须登录（router 级 ``require_auth``）——客户照片属隐私，公网不能让 URL 猜；
- ``storage_key`` 只当**相对上传根**的路径用，``app.storage.resolve_upload_path`` 做
  ``resolve()`` + ``is_relative_to`` 校验：绝对路径、``..``、软链接逃逸一律 404；
- ``FileResponse`` 流式发（不把整张图读进内存），并给 ``private`` 缓存头，
  避免中间代理缓存隐私照片。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.db import db_conn
from app.routers.auth import require_auth
from app.storage import MIME_BY_EXT, resolve_upload_path

router = APIRouter(
    prefix="/api/crm",
    tags=["attachments"],
    dependencies=[Depends(require_auth)],
)


@router.get("/attachments/{attachment_id}")
def get_attachment(attachment_id: int) -> FileResponse:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT storage_key, file_name, mime_type FROM attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")

    # 路径穿越/不存在都在这里抛 404（统一文案，不泄露服务器路径）
    path = resolve_upload_path(row["storage_key"])

    media_type = row["mime_type"] or MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )
