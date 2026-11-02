"""报价单下单表的不可变版本下载地址与旧履历兼容。"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from app.config.settings import settings
from app.quote_forms import QuoteFormParseError, inspect_excel_form, normalize_form_title
from app.storage import resolve_upload_path


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def form_version_token(storage_key: str) -> str:
    return base64.urlsafe_b64encode(storage_key.encode("utf-8")).decode("ascii").rstrip("=")


def storage_key_from_token(token: str) -> str | None:
    if not token or not _TOKEN_RE.fullmatch(token):
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        storage_key = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if Path(storage_key).suffix.lower() != ".xlsx":
        return None
    return storage_key


def form_download_url(storage_key: str, file_name: str | None) -> str:
    token = form_version_token(storage_key)
    safe_name = Path(file_name or Path(storage_key).name).name
    return (
        f"/api/crm/quotes/form-versions/{token}"
        f"?filename={quote(safe_name, safe='')}"
    )


def form_preview_url(form_sha256: str | None) -> str | None:
    if not form_sha256 or not re.fullmatch(r"[0-9a-f]{64}", form_sha256):
        return None
    preview_key = f"quote-previews/{form_sha256}.png"
    if not resolve_upload_path(preview_key, must_exist=False).is_file():
        return None
    return f"/api/crm/quotes/form-previews/{form_sha256}"


def _event_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


@lru_cache(maxsize=2048)
def _form_identity(path_text: str, size: int, mtime_ns: int) -> tuple[str | None, float]:
    del size, mtime_ns  # 仅作为缓存失效键
    path = Path(path_text)
    try:
        inspected = inspect_excel_form(path.read_bytes(), path.name)
    except (OSError, QuoteFormParseError):
        raise ValueError("无法识别下单表") from None
    return inspected["a1_value"], round(float(inspected["recognized_total"]), 2)


def resolve_legacy_form_storage_key(item: dict, event_at: str | None) -> str | None:
    """从旧履历的文件大小 + 写入时间定位当时落盘的 Excel。

    旧版本履历只记录了报价明细 ID，保存后再下载会误取最新文件。旧文件本身
    仍在上传目录中，且写入时间与履历创建时间只相差几毫秒，因此可安全回填。
    """

    try:
        expected_size = int(item.get("form_file_size") or 0)
    except (TypeError, ValueError):
        return None
    if expected_size <= 0:
        return None
    event_ts = _event_timestamp(event_at)
    if event_ts is None:
        return None

    root = settings.uploads_path.resolve()
    if not root.is_dir():
        return None
    try:
        expected_total = round(float(item.get("recognized_total") or 0), 2)
    except (TypeError, ValueError):
        expected_total = 0.0
    expected_a1 = normalize_form_title(item.get("a1_value"))
    candidates: list[tuple[float, str]] = []
    fallback: list[tuple[float, str]] = []
    for path in root.rglob("*.xlsx"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size != expected_size:
            continue
        delta = abs(stat.st_mtime - event_ts)
        if delta <= 5:
            fallback.append((delta, path.relative_to(root).as_posix()))
        # 旧履历的“发客户确认/重新报价”会沿用此前上传的文件，
        # 因此可在上传后的一段时间内按表头与识别合计继续匹配。
        if stat.st_mtime > event_ts + 5 or event_ts - stat.st_mtime > 3600:
            continue
        try:
            a1_value, recognized_total = _form_identity(
                str(path), stat.st_size, stat.st_mtime_ns
            )
        except ValueError:
            continue
        if normalize_form_title(a1_value) != expected_a1:
            continue
        if expected_total and recognized_total != expected_total:
            continue
        gap = max(0.0, event_ts - stat.st_mtime)
        candidates.append((gap, path.relative_to(root).as_posix()))
    if not candidates:
        candidates = fallback
    if not candidates:
        return None
    candidates.sort(key=lambda candidate: candidate[0])
    return candidates[0][1]


def enrich_quote_detail(detail: dict | None, event_at: str | None) -> dict | None:
    """把旧报价履历中的固定下载地址改写为当时文件版本。"""

    if not isinstance(detail, dict) or not isinstance(detail.get("items"), list):
        return detail
    for item in detail["items"]:
        if not isinstance(item, dict) or not item.get("form_file_name"):
            continue
        current_url = str(item.get("form_url") or "")
        if current_url.startswith("/api/crm/quotes/form-versions/"):
            continue
        storage_key = resolve_legacy_form_storage_key(item, event_at)
        if not storage_key:
            if current_url.startswith("/api/crm/quotes/items/"):
                item["form_url"] = None
                item["form_preview_url"] = None
            continue
        path = resolve_upload_path(storage_key)
        digest = item.get("form_sha256") or hashlib.sha256(path.read_bytes()).hexdigest()
        item["form_sha256"] = digest
        item["form_url"] = form_download_url(storage_key, item.get("form_file_name"))
        item["form_preview_url"] = form_preview_url(digest)
    return detail
