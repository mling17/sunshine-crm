"""Product master CRUD and product-to-opportunity usage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from app.db import db_conn
from app.errors import ApiError
from app.models import ProductDetailOut, ProductIn, ProductOut, ProductUpdate
from app.product_catalog import config_summary, parse_attributes
from app.routers.auth import require_auth
from app.security import now_iso
from app.storage import (
    DOC_MIME_BY_EXT,
    MAX_FILE_BYTES,
    resolve_upload_path,
    save_photo,
)


router = APIRouter(
    prefix="/api/crm",
    tags=["products"],
    dependencies=[Depends(require_auth)],
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _attributes(value: dict | None) -> dict:
    out = {}
    for key, item in (value or {}).items():
        if item in (None, "", [], {}):
            continue
        if key == "other" and isinstance(item, list):
            cleaned = [str(part).strip() for part in item if str(part).strip()]
            if cleaned:
                out[key] = cleaned
        else:
            out[str(key)] = str(item).strip()
    return out


def _check_dimensions(data: dict) -> None:
    for low, high, label in (
        ("min_width", "max_width", "宽"),
        ("min_height", "max_height", "高"),
    ):
        if data.get(low) is not None and data[low] < 0:
            raise ApiError(400, f"invalid_{low}", f"{label}最小值不能为负")
        if data.get(high) is not None and data[high] < 0:
            raise ApiError(400, f"invalid_{high}", f"{label}最大值不能为负")
        if data.get(low) is not None and data.get(high) is not None and data[low] > data[high]:
            raise ApiError(400, "invalid_dimension_range", f"{label}最小值不能大于最大值")


def _assert_code_unique(conn: sqlite3.Connection, code: str, exclude_id: int | None = None) -> None:
    sql = "SELECT id FROM products WHERE code = ? AND is_delete = 0"
    params: list[object] = [code]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_id)
    if conn.execute(sql, params).fetchone():
        raise ApiError(409, "product_code_exists", f"产品编码「{code}」已存在")


def _usage_maps(conn: sqlite3.Connection) -> tuple[dict[int, int], dict[int, int]]:
    deal_counts = {
        int(row["product_id"]): int(row["n"])
        for row in conn.execute(
            "SELECT product_id, COUNT(*) AS n FROM deals"
            " WHERE product_id IS NOT NULL AND is_delete = 0 GROUP BY product_id"
        )
    }
    order_counts = {
        int(row["product_id"]): int(row["n"])
        for row in conn.execute(
            "SELECT product_id, COUNT(*) AS n FROM orders"
            " WHERE product_id IS NOT NULL AND is_delete = 0 GROUP BY product_id"
        )
    }
    return deal_counts, order_counts


def _out(row, deal_counts: dict[int, int], order_counts: dict[int, int]) -> ProductOut:
    data = dict(row)
    data["attributes"] = parse_attributes(data.get("attributes"))
    data["config_summary"] = config_summary(data)
    data["deal_count"] = deal_counts.get(int(data["id"]), 0)
    data["order_count"] = order_counts.get(int(data["id"]), 0)
    data["form_available"] = False
    if data.get("form_storage_key"):
        try:
            resolve_upload_path(data["form_storage_key"])
            data["form_available"] = True
        except Exception:
            data["form_available"] = False
    return ProductOut(**data)


async def _save_product_form(form_file: UploadFile) -> dict:
    filename = Path(form_file.filename or "").name
    ext = Path(filename).suffix.lower()
    if ext not in {".xlsx", ".xls"}:
        raise ApiError(400, "product_form_type", "产品下单表必须是 .xlsx 或 .xls 文件")
    data = await form_file.read()
    if not data:
        raise ApiError(400, "product_form_empty", "产品下单表不能是空文件")
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(400, "product_form_too_large", "产品下单表不能超过 20MB")
    signature_ok = (
        ext == ".xlsx" and data.startswith(b"PK\x03\x04")
    ) or (
        ext == ".xls" and data.startswith(b"\xd0\xcf\x11\xe0")
    )
    if not signature_ok:
        raise ApiError(400, "product_form_invalid", "文件内容不是有效的 Excel 工作簿")
    storage_key = f"product_forms/{uuid.uuid4().hex}{ext}"
    save_photo(storage_key, data)
    return {
        "form_storage_key": storage_key,
        "form_file_name": filename or f"产品下单表{ext}",
        "form_file_size": len(data),
        "form_sha256": hashlib.sha256(data).hexdigest(),
        "form_uploaded_at": now_iso(),
    }


@router.get("/products", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(default=None, max_length=80),
    category: str | None = Query(default=None, max_length=32),
    series: str | None = Query(default=None, max_length=32),
    drive_type: str | None = Query(default=None, max_length=16),
    is_active: int | None = Query(default=None, ge=0, le=1),
) -> list[ProductOut]:
    where = ["is_delete = 0"]
    params: list[object] = []
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        where.append(
            "(code LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\'"
            " OR series LIKE ? ESCAPE '\\' OR structure LIKE ? ESCAPE '\\')"
        )
        params.extend([like, like, like, like])
    if category:
        where.append("category = ?")
        params.append(category.strip())
    if series:
        where.append("series = ?")
        params.append(series.strip())
    if drive_type:
        where.append("drive_type = ?")
        params.append(drive_type.strip())
    if is_active is not None:
        where.append("is_active = ?")
        params.append(is_active)

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM products WHERE " + " AND ".join(where)
            + " ORDER BY CASE WHEN category='天窗' THEN 0 ELSE 1 END, series, code, id",
            params,
        ).fetchall()
        deal_counts, order_counts = _usage_maps(conn)
    return [_out(row, deal_counts, order_counts) for row in rows]


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def get_product_detail(product_id: int) -> ProductDetailOut:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ? AND is_delete = 0", (product_id,)
        ).fetchone()
        if row is None:
            raise ApiError(404, "product_not_found", "产品不存在")
        deal_counts, order_counts = _usage_maps(conn)
        data = _out(row, deal_counts, order_counts).model_dump()
        data["deals"] = [
            dict(item)
            for item in conn.execute(
                """
                SELECT d.id, d.amount, d.stage, d.spec, d.created_at, d.order_id,
                       c.name AS customer_name
                  FROM deals d
             LEFT JOIN customers c ON c.id = d.customer_id
                 WHERE d.product_id = ? AND d.is_delete = 0
              ORDER BY d.id DESC
                """,
                (product_id,),
            ).fetchall()
        ]
    return ProductDetailOut(**data)


@router.post("/products", response_model=ProductOut)
async def create_product(
    payload: str = Form(..., description="JSON 字符串，结构同 ProductIn"),
    form_file: UploadFile = File(..., description="对应的 Excel 下单表"),
) -> ProductOut:
    try:
        parsed = ProductIn.model_validate_json(payload)
    except ValueError as exc:
        raise ApiError(400, "invalid_product_payload", f"产品参数格式错误：{exc}") from exc
    data = parsed.model_dump()
    data["code"] = (_clean(data.get("code")) or "").upper()
    data["name"] = _clean(data.get("name")) or ""
    data["category"] = _clean(data.get("category")) or "天窗"
    if not data["code"]:
        raise ApiError(400, "product_code_required", "产品编码不能为空")
    if not data["name"]:
        raise ApiError(400, "product_name_required", "产品名称不能为空")
    _check_dimensions(data)
    seed_key = f"manual:{uuid.uuid4().hex}"
    with db_conn() as conn:
        _assert_code_unique(conn, data["code"])
    form_meta = await _save_product_form(form_file)
    now = now_iso()
    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO products (
                seed_key, code, name, category, series, structure, opening_mode,
                drive_type, frame_type, leaf_type, edge_type, leaf_count,
                min_width, max_width, min_height, max_height, attributes,
                source_template, form_storage_key, form_file_name, form_file_size,
                form_sha256, form_uploaded_at, description, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seed_key,
                data["code"],
                data["name"],
                data["category"],
                _clean(data.get("series")),
                _clean(data.get("structure")),
                _clean(data.get("opening_mode")),
                _clean(data.get("drive_type")),
                _clean(data.get("frame_type")),
                _clean(data.get("leaf_type")),
                _clean(data.get("edge_type")),
                data.get("leaf_count"),
                data.get("min_width"),
                data.get("max_width"),
                data.get("min_height"),
                data.get("max_height"),
                json.dumps(_attributes(data.get("attributes")), ensure_ascii=False),
                _clean(data.get("source_template")) or form_meta["form_file_name"],
                form_meta["form_storage_key"],
                form_meta["form_file_name"],
                form_meta["form_file_size"],
                form_meta["form_sha256"],
                form_meta["form_uploaded_at"],
                _clean(data.get("description")),
                1 if data.get("is_active", True) else 0,
                now,
                now,
            ),
        )
        product_id = int(cur.lastrowid or 0)
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        deal_counts, order_counts = _usage_maps(conn)
    return _out(row, deal_counts, order_counts)


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate) -> ProductOut:
    updates = payload.model_dump(exclude_unset=True)
    with db_conn() as conn:
        old = conn.execute(
            "SELECT * FROM products WHERE id = ? AND is_delete = 0", (product_id,)
        ).fetchone()
        if old is None:
            raise ApiError(404, "product_not_found", "产品不存在")

        if "code" in updates:
            updates["code"] = (_clean(updates["code"]) or "").upper()
            if not updates["code"]:
                raise ApiError(400, "product_code_required", "产品编码不能为空")
            _assert_code_unique(conn, updates["code"], exclude_id=product_id)
        if "name" in updates:
            updates["name"] = _clean(updates["name"]) or ""
            if not updates["name"]:
                raise ApiError(400, "product_name_required", "产品名称不能为空")
        for key in ("category", "series", "structure", "opening_mode", "drive_type",
                    "frame_type", "leaf_type", "edge_type", "source_template", "description"):
            if key in updates:
                updates[key] = _clean(updates[key])
        if "category" in updates and not updates["category"]:
            raise ApiError(400, "product_category_required", "产品分类不能为空")
        if "attributes" in updates:
            updates["attributes"] = json.dumps(
                _attributes(updates["attributes"]), ensure_ascii=False
            )
        if "is_active" in updates:
            updates["is_active"] = 1 if updates["is_active"] else 0
            if updates["is_active"] and not old["form_storage_key"]:
                raise ApiError(400, "product_form_required", "启用产品前必须上传对应的 Excel 下单表")
        _check_dimensions({**dict(old), **updates})

        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(
                f"UPDATE products SET {assignments}, updated_at = ? WHERE id = ?",
                [*updates.values(), now_iso(), product_id],
            )
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        deal_counts, order_counts = _usage_maps(conn)
    return _out(row, deal_counts, order_counts)


@router.put("/products/{product_id}/form-file", response_model=ProductOut)
async def replace_product_form(
    product_id: int,
    form_file: UploadFile = File(...),
) -> ProductOut:
    form_meta = await _save_product_form(form_file)
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ? AND is_delete = 0", (product_id,)
        ).fetchone()
        if row is None:
            raise ApiError(404, "product_not_found", "产品不存在")
        conn.execute(
            """
            UPDATE products
               SET form_storage_key = ?, form_file_name = ?, form_file_size = ?,
                   form_sha256 = ?, form_uploaded_at = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                form_meta["form_storage_key"],
                form_meta["form_file_name"],
                form_meta["form_file_size"],
                form_meta["form_sha256"],
                form_meta["form_uploaded_at"],
                now_iso(),
                product_id,
            ),
        )
        fresh = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        deal_counts, order_counts = _usage_maps(conn)
    return _out(fresh, deal_counts, order_counts)


@router.get("/products/{product_id}/form-file")
def download_product_form(product_id: int) -> FileResponse:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT form_storage_key, form_file_name FROM products"
            " WHERE id = ? AND is_delete = 0",
            (product_id,),
        ).fetchone()
    if row is None or not row["form_storage_key"]:
        raise ApiError(404, "product_form_not_found", "产品未关联 Excel 下单表")
    path = resolve_upload_path(row["form_storage_key"])
    extension = path.suffix.lower()
    return FileResponse(
        path,
        media_type=DOC_MIME_BY_EXT.get(extension, "application/octet-stream"),
        filename=row["form_file_name"] or path.name,
        content_disposition_type="attachment",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/products/{product_id}", response_model=dict)
def delete_product(product_id: int) -> dict:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT id FROM products WHERE id = ? AND is_delete = 0", (product_id,)
        ).fetchone()
        if row is None:
            raise ApiError(404, "product_not_found", "产品不存在")
        conn.execute(
            "UPDATE products SET is_delete = 1, is_active = 0, updated_at = ? WHERE id = ?",
            (now_iso(), product_id),
        )
    return {"ok": True, "id": product_id}
