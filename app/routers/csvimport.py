"""CSV 导入（存量 Excel 数据迁移）：preview + commit。

分两步，都是为了「不等表样、手动映射列」：

1. ``POST /api/crm/import/preview``（multipart，字段名 ``file``）
   用 stdlib ``csv`` 解析表头 + 前 5 行，返回 ``headers / preview / total_rows /
   suggested_mapping``，并把原文件缓存到 ``<uploads>/_import_cache/<token>.csv``
   （2 小时 TTL），把 token 作为 ``file_ref`` 回给前端 —— commit 时不用再传一次文件。
   **.xlsx 不解析**（V1.5 才上 openpyxl）：认出来就返回 ``kind=xlsx_unsupported``
   + 友好提示，200 不报错、不崩溃。
2. ``POST /api/crm/import/commit``：支持两种请求体
   - JSON ``{file_ref, column_mapping, source_name}``（先 preview 后 commit，推荐）；
   - multipart ``file + column_mapping(JSON 字符串)``（一次性上传+导入）。
   按映射写 ``customers``，落 ``import_log`` 审计；**不传映射时自动复用上一次**
   （``import_log`` 里最近一条），换个人重导同一份表不用再点一遍映射。
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config.settings import settings
from app.db import db_conn
from app.models import (
    ImportCommitIn,
    ImportCommitOut,
    ImportFieldOut,
    ImportPreviewOut,
)
from app.routers.auth import require_auth
from app.security import now_iso

router = APIRouter(
    prefix="/api/crm",
    tags=["import"],
    dependencies=[Depends(require_auth)],
)

#: 系统字段（唯一来源：校验、下拉、提示都从这里派生）
FIELD_LABELS: dict[str, str] = {
    "name": "姓名",
    "phone": "电话",
    "wechat": "微信",
    "location": "楼盘/安装地址",
    "house_note": "户型/备注",
}
SYSTEM_FIELDS = [
    ImportFieldOut(key=key, label=label, required=(key == "name"))
    for key, label in FIELD_LABELS.items()
]

#: 表头 → 系统字段的猜测表（只是建议值，前端仍可手改）
HEADER_ALIASES: dict[str, str] = {
    "姓名": "name",
    "名字": "name",
    "客户姓名": "name",
    "客户": "name",
    "name": "name",
    "电话": "phone",
    "手机": "phone",
    "手机号": "phone",
    "联系电话": "phone",
    "phone": "phone",
    "微信": "wechat",
    "微信号": "wechat",
    "wechat": "wechat",
    "楼盘": "location",
    "小区": "location",
    "地址": "location",
    "项目": "location",
    "安装地址": "location",
    "location": "location",
    "户型": "house_note",
    "备注": "house_note",
    "说明": "house_note",
    "house_note": "house_note",
}

PREVIEW_ROWS = 5
MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
CACHE_TTL_SECONDS = 2 * 3600

_FILE_REF_RE = re.compile(r"^[0-9a-f]{32}$")
_XLSX_MAGIC = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")  # zip(xlsx) / OLE 老 xls
_XLSX_HINT = "暂不支持直接读 Excel（.xlsx/.xls）：请在 Excel 里「另存为 CSV（逗号分隔）」后再上传，V1.5 才会支持直接解析。"


@dataclass
class ParsedCsv:
    encoding: str
    delimiter: str
    headers: list[str]
    rows: list[list[str]]


# ---------------- 解析 ----------------


def _cache_dir() -> Path:
    return settings.uploads_path / "_import_cache"


def _looks_like_xlsx(filename: str, data: bytes) -> bool:
    if Path(filename or "").suffix.lower() in {".xlsx", ".xls"}:
        return True
    return any(data.startswith(magic) for magic in _XLSX_MAGIC)


def _decode_csv(data: bytes) -> tuple[str, str]:
    """UTF-8(带/不带 BOM) → GB18030（兼容 GBK/GB2312，Excel 中文默认另存就是这个）。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=400, detail="无法识别文件编码，请在 Excel 里另存为「CSV UTF-8」后再试"
    )


def _sniff_delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    counts = {sep: first_line.count(sep) for sep in (",", ";", "\t", "|")}
    best_sep, best_count = max(counts.items(), key=lambda item: item[1])
    return best_sep if best_count else ","


def _parse_csv(data: bytes) -> ParsedCsv:
    if not data.strip():
        raise HTTPException(status_code=400, detail="文件是空的")
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"CSV 文件超过 {MAX_CSV_BYTES // (1024 * 1024)}MB，请拆分后再导入",
        )

    text, encoding = _decode_csv(data)
    delimiter = _sniff_delimiter(text)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        raw_rows = list(reader)
    except csv.Error as exc:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败：{exc}") from None

    # 丢掉整行空白的行（Excel 导出尾部常带一堆 ,,,）
    raw_rows = [row for row in raw_rows if any((cell or "").strip() for cell in row)]
    if not raw_rows:
        raise HTTPException(status_code=400, detail="文件只有空行，没有表头")

    headers = [(cell or "").strip() for cell in raw_rows[0]]
    if not any(headers):
        raise HTTPException(status_code=400, detail="第一行必须是表头（列名）")
    duplicates = {name for name in headers if headers.count(name) > 1}
    if duplicates:
        raise HTTPException(
            status_code=400,
            detail="表头有重复列名：" + "、".join(sorted(duplicates)),
        )

    width = len(headers)
    rows: list[list[str]] = []
    for row in raw_rows[1:]:
        normalized = [(cell or "").strip() for cell in row[:width]]
        normalized += [""] * (width - len(normalized))
        rows.append(normalized)

    return ParsedCsv(encoding=encoding, delimiter=delimiter, headers=headers, rows=rows)


def _suggest_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        field = HEADER_ALIASES.get(header.strip().lower()) or HEADER_ALIASES.get(header.strip())
        if field and field not in mapping.values():
            mapping[header] = field
    return mapping


# ---------------- 预览缓存 ----------------


def _cleanup_cache() -> None:
    directory = _cache_dir()
    if not directory.is_dir():
        return
    deadline = time.time() - CACHE_TTL_SECONDS
    for path in directory.glob("*.csv"):
        try:
            if path.stat().st_mtime < deadline:
                path.unlink(missing_ok=True)
        except OSError:  # 清理失败不影响主流程
            continue


def _cache_upload(data: bytes) -> str:
    directory = _cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    _cleanup_cache()
    token = uuid.uuid4().hex
    (directory / f"{token}.csv").write_bytes(data)
    return token


def _read_cached(file_ref: str) -> bytes:
    """file_ref 只接受 32 位 hex —— 直接杜绝用 ../ 之类的 token 读别的文件。"""
    token = (file_ref or "").strip()
    if not _FILE_REF_RE.match(token):
        raise HTTPException(status_code=400, detail="file_ref 不合法，请重新上传文件")
    path = _cache_dir() / f"{token}.csv"
    if not path.is_file():
        raise HTTPException(
            status_code=400, detail="预览文件已过期，请重新上传 CSV 后再导入"
        )
    return path.read_bytes()


def _drop_cached(file_ref: str) -> None:
    if _FILE_REF_RE.match((file_ref or "").strip()):
        (_cache_dir() / f"{file_ref.strip()}.csv").unlink(missing_ok=True)


def _last_mapping(conn) -> dict[str, str] | None:
    row = conn.execute(
        """
        SELECT column_mapping FROM import_log
        WHERE column_mapping IS NOT NULL AND TRIM(column_mapping) <> ''
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    try:
        parsed = json.loads(row["column_mapping"])
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


# ---------------- 映射校验 ----------------


def _normalize_mapping(raw: dict | None, headers: list[str]) -> dict[str, str]:
    if not isinstance(raw, dict) or not raw:
        raise HTTPException(
            status_code=400,
            detail="请先做列映射：把 CSV 的列对应到系统字段（至少「姓名」）",
        )

    mapping: dict[str, str] = {}
    for header, field in raw.items():
        field_name = field.strip() if isinstance(field, str) else ""
        if not field_name:  # 前端把未映射的列留空，忽略
            continue
        if field_name not in FIELD_LABELS:
            raise HTTPException(
                status_code=400,
                detail=f"未知字段 {field_name!r}，可选：" + "、".join(FIELD_LABELS),
            )
        mapping[str(header).strip()] = field_name

    missing = [header for header in mapping if header not in headers]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="映射的列在文件里不存在：" + "、".join(missing) + "，请重新选择列",
        )
    if "name" not in mapping.values():
        raise HTTPException(
            status_code=400, detail="必须把某一列映射到「姓名」，否则无法建客户"
        )
    return mapping


# ---------------- 路由 ----------------


@router.post("/import/preview", response_model=ImportPreviewOut)
async def preview_import(file: UploadFile = File(..., description="CSV 文件")) -> ImportPreviewOut:
    filename = file.filename or ""
    data = await file.read()

    if _looks_like_xlsx(filename, data):
        # 友好提示：200 + 空表头，前端直接显示 message，不弹“导入失败”
        return ImportPreviewOut(
            ok=False,
            kind="xlsx_unsupported",
            file_name=filename,
            system_fields=SYSTEM_FIELDS,
            message=_XLSX_HINT,
        )

    parsed = _parse_csv(data)
    file_ref = _cache_upload(data)

    with db_conn() as conn:
        last_mapping = _last_mapping(conn)

    suggested = _suggest_mapping(parsed.headers)
    return ImportPreviewOut(
        ok=True,
        kind="csv",
        file_name=filename,
        file_ref=file_ref,
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
        headers=parsed.headers,
        preview=[
            dict(zip(parsed.headers, row)) for row in parsed.rows[:PREVIEW_ROWS]
        ],
        total_rows=len(parsed.rows),
        suggested_mapping=suggested,
        last_mapping=last_mapping,
        system_fields=SYSTEM_FIELDS,
        message="" if parsed.rows else "文件里只有表头，没有数据行",
    )


async def _read_commit_request(request: Request) -> tuple[bytes | None, str | None, dict | None, str | None]:
    """兼容 JSON 与 multipart 两种提交方式，返回 ``(file_bytes, file_ref, mapping, source_name)``。"""
    content_type = (request.headers.get("content-type") or "").lower()

    if content_type.startswith("multipart/form-data") or content_type.startswith(
        "application/x-www-form-urlencoded"
    ):
        form = await request.form()
        upload = form.get("file")
        if isinstance(upload, StarletteUploadFile):
            data: bytes | None = await upload.read()
            upload_name: str | None = upload.filename
        else:
            data = None
            upload_name = None

        raw_mapping = form.get("column_mapping")
        mapping = None
        if isinstance(raw_mapping, str) and raw_mapping.strip():
            try:
                mapping = json.loads(raw_mapping)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="column_mapping 必须是 JSON 对象") from None

        raw_source = form.get("source_name")
        source = raw_source if isinstance(raw_source, str) and raw_source else upload_name
        raw_ref = form.get("file_ref")
        file_ref = raw_ref if isinstance(raw_ref, str) and raw_ref else None
        return data, file_ref, mapping, source

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 或 multipart") from None

    try:
        payload = ImportCommitIn(**body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"参数错误：{exc.errors()}") from None

    return None, payload.file_ref, payload.column_mapping, payload.source_name


@router.post("/import/commit", response_model=ImportCommitOut)
async def commit_import(request: Request) -> ImportCommitOut:
    data, file_ref, mapping_raw, source_name = await _read_commit_request(request)

    if data is None:
        if not file_ref:
            raise HTTPException(status_code=400, detail="缺少 file_ref 或上传文件 file")
        data = _read_cached(file_ref)

    filename = source_name or "import.csv"
    if _looks_like_xlsx(filename, data):
        raise HTTPException(status_code=400, detail=_XLSX_HINT)

    parsed = _parse_csv(data)
    if len(parsed.rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多导入 {MAX_IMPORT_ROWS} 行，请拆分文件",
        )

    with db_conn() as conn:
        if mapping_raw:
            mapping = _normalize_mapping(mapping_raw, parsed.headers)
            mapping_reused = False
        else:
            last_mapping = _last_mapping(conn)
            if last_mapping is None:
                raise HTTPException(
                    status_code=400,
                    detail="还没有可复用的映射，请先做列映射（至少「姓名」）",
                )
            mapping = _normalize_mapping(last_mapping, parsed.headers)
            mapping_reused = True

        # 表头 → 列下标；映射里的表头已校验存在
        field_index = {field: parsed.headers.index(header) for header, field in mapping.items()}

        now = now_iso()
        imported = 0
        skipped = 0
        for row in parsed.rows:
            name = row[field_index["name"]].strip()
            if not name:
                skipped += 1
                continue

            values = {
                field: (row[index].strip() or None) if field != "name" else name
                for field, index in field_index.items()
            }
            conn.execute(
                """
                INSERT INTO customers (name, phone, wechat, location, house_note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["name"],
                    values.get("phone"),
                    values.get("wechat"),
                    values.get("location"),
                    values.get("house_note"),
                    now,
                    now,
                ),
            )
            imported += 1

        cur = conn.execute(
            """
            INSERT INTO import_log (source_name, column_mapping, row_count, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                filename,
                json.dumps(mapping, ensure_ascii=False),
                imported,
                now,
            ),
        )
        import_log_id = int(cur.lastrowid or 0)

    # 导完就丢掉缓存文件：避免同一个 file_ref 被重复点两次导两遍
    if file_ref:
        _drop_cached(file_ref)

    return ImportCommitOut(
        ok=True,
        imported=imported,
        skipped=skipped,
        total_rows=len(parsed.rows),
        import_log_id=import_log_id,
        mapping_used=mapping,
        mapping_reused=mapping_reused,
        source_name=filename,
    )
