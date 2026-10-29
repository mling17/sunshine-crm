"""照片落盘 / 取盘（本地目录，零第三方存储）。

约定（本模块是唯一出口，别在 router 里自己拼路径）：

- 上传根目录 = ``settings.uploads_path``（生产 ``/opt/data/crm/uploads``，
  测试/迁移时可用 ``CRM_UPLOADS`` 指到别处 —— 所以**不要**把 ``uploads/``
  前缀写进 key，否则换根目录就失效）；
- ``storage_key`` = ``YYYY/MM/DD/<uuid>.<ext>``，**相对上传根目录**；
- 取文件一律走 ``resolve_upload_path``：``resolve()`` 之后必须仍在上传根内，
  绝对路径、``..``、软链接逃逸一律 404（不区分「不存在」与「非法」，不泄露路径）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from app.config.settings import settings

#: 允许的图片扩展名（只存图，杜绝把 .html/.svg 之类的可执行内容塞进上传目录）
ALLOWED_IMAGE_EXT: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
)

MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

EXT_BY_MIME: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

#: 单张照片上限（微信原图一般 2~5MB；3 张 × 20MB 仍远低于 nginx 的 100M）
MAX_PHOTO_BYTES = 20 * 1024 * 1024


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="附件不存在")


def ext_and_mime(filename: str | None, content_type: str | None) -> tuple[str, str]:
    """从文件名/Content-Type 定扩展名与 mime；不是图片就 400。"""
    suffix = Path((filename or "").strip()).suffix.lower()
    mime = (content_type or "").split(";")[0].strip().lower()

    ext = suffix if suffix in ALLOWED_IMAGE_EXT else EXT_BY_MIME.get(mime, "")
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="只支持图片文件（jpg/jpeg/png/gif/webp/bmp/heic）",
        )

    if not mime.startswith("image/"):
        mime = MIME_BY_EXT[ext]
    return ext, mime


def new_storage_key(ext: str, now: datetime | None = None) -> str:
    """``YYYY/MM/DD/<uuid><ext>``（按**服务器本地日期**分目录，和待办口径一致）。"""
    moment = now or datetime.now()
    return (
        f"{moment:%Y/%m/%d}/{uuid.uuid4().hex}{ext}"
    )


def save_photo(storage_key: str, data: bytes) -> Path:
    """把字节写到上传根下的 ``storage_key``；目录按需创建。"""
    target = resolve_upload_path(storage_key, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def resolve_upload_path(storage_key: str, *, must_exist: bool = True) -> Path:
    """key → 上传根内的绝对路径；越界/绝对路径一律 404。

    ``resolve()`` 会展开 ``..`` 与软链接，再用 ``is_relative_to`` 判定，
    因此 ``../../etc/passwd``、``/etc/passwd``、指向外部的软链接都过不去。
    """
    key = (storage_key or "").strip()
    if not key or "\x00" in key:
        raise _not_found()

    relative = Path(key)
    if relative.is_absolute():
        raise _not_found()

    root = settings.uploads_path.resolve()
    target = (root / relative).resolve()
    # target == root 说明 key 是 "." 之类，也不是文件
    if target == root or not target.is_relative_to(root):
        raise _not_found()
    if must_exist and not target.is_file():
        raise _not_found()
    return target
