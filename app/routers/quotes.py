"""商机报价单：产品明细、Excel 下单表、客户确认和转订单。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.db import db_conn
from app.errors import ApiError
from app.models import AttachmentOut, QuoteIn, QuoteItemOut, QuoteOut
from app.product_catalog import get_product, product_snapshot
from app.quote_forms import (
    QuoteFormParseError,
    inspect_excel_form,
    normalize_form_title,
    read_sheet1_a1,
)
from app.routers.auth import require_auth
from app.security import now_iso, now_local_iso
from app.services import next_no
from app.storage import (
    DOC_MIME_BY_EXT,
    MAX_FILE_BYTES,
    ext_and_mime,
    new_storage_key,
    resolve_upload_path,
    save_photo,
)
from app.timeline import add_entry, entries_for

router = APIRouter(
    prefix="/api/crm",
    tags=["quotes"],
    dependencies=[Depends(require_auth)],
)


def _deal(conn, deal_id: int):
    row = conn.execute(
        "SELECT * FROM deals WHERE id = ? AND is_delete = 0", (deal_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="商机不存在")
    return row


def _quote(conn, quote_id: int):
    row = conn.execute(
        "SELECT * FROM deal_quotes WHERE id = ? AND is_delete = 0", (quote_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="报价单不存在")
    return row


def _quote_items(conn, quote_id: int):
    return conn.execute(
        "SELECT * FROM quote_items WHERE quote_id = ? AND is_delete = 0"
        " ORDER BY sort, id",
        (quote_id,),
    ).fetchall()


def _assert_editable(conn, quote_id: int):
    quote = _quote(conn, quote_id)
    deal = _deal(conn, quote["deal_id"])
    if deal["order_id"] is not None or deal["stage"] == "lost":
        raise ApiError(
            status_code=409,
            code="deal_locked",
            message="商机已转订单或已流失，不能修改报价单",
        )
    if quote["status"] != "draft":
        raise ApiError(
            status_code=409,
            code="quote_locked",
            message="报价单已确认或作废，不能修改",
        )
    return quote, deal


def _item_out(conn, row) -> QuoteItemOut:
    data = dict(row)
    raw_content = data.pop("form_content_json", None)
    try:
        content = json.loads(raw_content) if raw_content else {}
    except (TypeError, ValueError):
        content = {}
    product = conn.execute(
        "SELECT form_storage_key FROM products WHERE id = ? AND is_delete = 0",
        (data["product_id"],),
    ).fetchone()
    data["form_available"] = bool(
        data.get("form_storage_key")
        and resolve_upload_path(data["form_storage_key"], must_exist=False).is_file()
    )
    data["form_content"] = content
    data["form_url"] = (
        f"/api/crm/quotes/items/{data['id']}/form" if data["form_available"] else None
    )
    preview_key = data.get("form_preview_storage_key")
    data["form_preview_url"] = (
        f"/api/crm/quotes/items/{data['id']}/form-preview"
        if preview_key and resolve_upload_path(preview_key, must_exist=False).is_file()
        else None
    )
    data["template_url"] = (
        f"/api/crm/products/{data['product_id']}/form-file"
        if product and product["form_storage_key"]
        else None
    )
    return QuoteItemOut(**data)


def _quote_out(conn, row) -> QuoteOut:
    data = dict(row)
    data["items"] = [_item_out(conn, item) for item in _quote_items(conn, row["id"])]
    order = (
        conn.execute(
            "SELECT order_no FROM orders WHERE id = ? AND is_delete = 0",
            (row["order_id"],),
        ).fetchone()
        if row["order_id"]
        else None
    )
    data["order_no"] = order["order_no"] if order else None
    data["confirmation_files"] = [
        AttachmentOut(**dict(item))
        for item in conn.execute(
            "SELECT * FROM attachments"
            " WHERE object_type = 'quote_confirmation' AND object_id = ?"
            " ORDER BY id",
            (row["id"],),
        ).fetchall()
    ]
    return QuoteOut(**data)


def _sync_amount(conn, quote_id: int) -> float:
    total = round(
        sum(
            float(row["amount"] or 0)
            for row in _quote_items(conn, quote_id)
        ),
        2,
    )
    conn.execute(
        "UPDATE deal_quotes SET amount = ?, updated_at = ? WHERE id = ?",
        (total, now_iso(), quote_id),
    )
    return total


async def _read_xlsx(upload: UploadFile) -> tuple[str, bytes]:
    filename = Path(upload.filename or "").name
    if Path(filename).suffix.lower() != ".xlsx":
        raise ApiError(
            status_code=400,
            code="quote_form_xlsx_required",
            message="报价单下单表必须是 .xlsx",
        )
    data = await upload.read()
    if not data:
        raise ApiError(status_code=400, code="quote_form_empty", message="下单表是空文件")
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(
            status_code=400,
            code="quote_form_too_large",
            message=f"下单表不能超过 {MAX_FILE_BYTES // (1024 * 1024)}MB",
        )
    return filename, data


def _store_form(filename: str, data: bytes) -> tuple[str, str]:
    key = new_storage_key(".xlsx")
    save_photo(key, data)
    return key, hashlib.sha256(data).hexdigest()


def _product_a1(product: dict) -> str | None:
    key = product.get("form_storage_key")
    if not key:
        return None
    path = resolve_upload_path(key)
    return read_sheet1_a1(path.read_bytes())


def _inspect_upload(product: dict, filename: str, data: bytes) -> dict:
    try:
        inspected = inspect_excel_form(data, filename)
    except QuoteFormParseError as exc:
        raise ApiError(400, "quote_form_parse_failed", str(exc)) from exc
    expected_a1 = _product_a1(product)
    if not expected_a1:
        raise ApiError(
            400,
            "product_form_a1_missing",
            "关联产品的原始下单表没有 A1 标题，无法校验",
        )
    if normalize_form_title(inspected["a1_value"]) != normalize_form_title(expected_a1):
        raise ApiError(
            400,
            "quote_form_product_mismatch",
            f"下单表 A1 为「{inspected['a1_value'] or ''}」，"
            f"与关联产品要求的「{expected_a1}」不一致",
        )
    digest = hashlib.sha256(data).hexdigest()
    preview_key = f"quote-previews/{digest}.png"
    save_photo(preview_key, inspected.pop("image_bytes"))
    inspected["preview_token"] = digest
    inspected["preview_storage_key"] = preview_key
    inspected["expected_a1"] = expected_a1
    return inspected


@router.get("/deals/{deal_id}/quotes", response_model=list[QuoteOut])
def list_quotes(deal_id: int) -> list[QuoteOut]:
    with db_conn() as conn:
        _deal(conn, deal_id)
        rows = conn.execute(
            "SELECT * FROM deal_quotes WHERE deal_id = ? AND is_delete = 0 ORDER BY id DESC",
            (deal_id,),
        ).fetchall()
        return [_quote_out(conn, row) for row in rows]


@router.get("/quotes/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: int) -> QuoteOut:
    with db_conn() as conn:
        return _quote_out(conn, _quote(conn, quote_id))


@router.post("/deals/{deal_id}/quotes", response_model=QuoteOut)
def create_quote(deal_id: int, payload: QuoteIn) -> QuoteOut:
    with db_conn() as conn:
        deal = _deal(conn, deal_id)
        if deal["order_id"] is not None or deal["stage"] == "lost":
            raise ApiError(
                status_code=409,
                code="deal_locked",
                message="商机已转订单或已流失，不能新建报价单",
            )
        confirmed = conn.execute(
            "SELECT quote_no FROM deal_quotes"
            " WHERE deal_id = ? AND status = 'confirmed' AND is_delete = 0",
            (deal_id,),
        ).fetchone()
        if confirmed:
            raise ApiError(
                status_code=409,
                code="quote_already_confirmed",
                message=f"该商机已有客户确认的报价单 {confirmed['quote_no']}",
            )
        quote_no = next_no(
            conn, "deal_quotes", "quote_no", "QT", now_local_iso()[:8]
        )
        title = (payload.title or "").strip() or quote_no
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO deal_quotes (quote_no, deal_id, customer_id, title, note,"
            " status, amount, created_at, updated_at, create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, 'draft', 0, ?, ?, '', '', 0)",
            (quote_no, deal_id, deal["customer_id"], title, payload.note, now, now),
        )
        quote_id = int(cur.lastrowid or 0)
        add_entry(
            conn,
            object_type="deal",
            object_id=deal_id,
            kind="quote",
            customer_id=deal["customer_id"],
            deal_id=deal_id,
            quote_id=quote_id,
            content=f"创建报价单 {quote_no}",
            detail={"quote_id": quote_id, "quote_no": quote_no},
        )
        return _quote_out(conn, _quote(conn, quote_id))


@router.post("/quotes/form-preview", response_model=dict)
async def preview_quote_form(
    product_id: int = Form(...),
    form_file: UploadFile = File(...),
) -> dict:
    """保存前识别 Sheet1：校验 A1、提取合计金额并生成数据区图片。"""
    filename, data = await _read_xlsx(form_file)
    with db_conn() as conn:
        product = get_product(conn, int(product_id), active_only=True)
    if product is None:
        raise ApiError(400, "product_not_found", "关联产品不存在或已停用")
    inspected = _inspect_upload(product, filename, data)
    return {
        "ok": True,
        "preview_token": inspected["preview_token"],
        "filename": filename,
        "a1_value": inspected["a1_value"],
        "expected_a1": inspected["expected_a1"],
        "recognized_total": inspected["recognized_total"],
        "amount_cell": inspected["amount_cell"],
        "sheet_content": inspected["sheet_content"],
        "image_url": (
            f"/api/crm/quotes/form-previews/{inspected['preview_token']}"
        ),
    }


@router.post("/quotes/{quote_id}/items", response_model=QuoteOut)
async def add_quote_item(
    quote_id: int,
    product_id: int = Form(...),
    preview_token: str = Form(...),
    note: str | None = Form(default=None),
    form_file: UploadFile = File(...),
) -> QuoteOut:
    filename, data = await _read_xlsx(form_file)
    with db_conn() as conn:
        quote, deal = _assert_editable(conn, quote_id)
        product = get_product(conn, int(product_id), active_only=True)
        if product is None:
            raise ApiError(400, "product_not_found", "关联产品不存在或已停用")
        inspected = _inspect_upload(product, filename, data)
        if inspected["preview_token"] != preview_token:
            raise ApiError(
                409,
                "quote_form_preview_stale",
                "下单表在预览后发生变化，请重新识别",
            )
        amount = round(float(inspected["recognized_total"]), 2)
        key, digest = _store_form(filename, data)
        snapshot = product_snapshot(product)
        next_sort = conn.execute(
            "SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM quote_items"
            " WHERE quote_id = ? AND is_delete = 0",
            (quote_id,),
        ).fetchone()["n"]
        now = now_iso()
        conn.execute(
            "INSERT INTO quote_items (quote_id, deal_id, product_id,"
            " product_code_snapshot, product_name_snapshot, product_config_snapshot,"
            " product_type, model, drive_type, quantity, spec, production_spec,"
            " unit_price, amount, note, form_storage_key, form_file_name, form_file_size,"
            " form_mime_type, form_sha256, form_content_json, recognized_total,"
            " a1_value, amount_cell, form_preview_storage_key, sort, created_at, updated_at,"
            " create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                quote_id,
                quote["deal_id"],
                snapshot["product_id"],
                snapshot["product_code_snapshot"],
                snapshot["product_name_snapshot"],
                snapshot["product_config_snapshot"],
                snapshot["product_type"],
                snapshot["model"],
                snapshot["drive_type"],
                1,
                None,
                None,
                amount,
                amount,
                (note or "").strip() or None,
                key,
                filename,
                len(data),
                DOC_MIME_BY_EXT[".xlsx"],
                digest,
                json.dumps(
                    {
                        "filename": filename,
                        "sheets": [inspected["sheet_content"]],
                        "sheet_count": 1,
                    },
                    ensure_ascii=False,
                ),
                amount,
                inspected["a1_value"],
                inspected["amount_cell"],
                inspected["preview_storage_key"],
                int(next_sort),
                now,
                now,
                "",
                "",
                0,
            ),
        )
        total = _sync_amount(conn, quote_id)
        add_entry(
            conn,
            object_type="deal",
            object_id=quote["deal_id"],
            kind="quote",
            customer_id=quote["customer_id"],
            deal_id=quote["deal_id"],
            quote_id=quote_id,
            content=(
                f"报价单 {quote['quote_no']} 添加产品"
                f" {snapshot['product_name_snapshot'] or snapshot['product_code_snapshot']}"
                f"，上传下单表 {filename}，识别合计 ¥{amount:,.2f}"
            ),
            detail={"quote_id": quote_id, "amount": total},
        )
        return _quote_out(conn, _quote(conn, quote_id))


@router.put("/quotes/items/{item_id}", response_model=QuoteOut)
async def update_quote_item(
    item_id: int,
    product_id: int | None = Form(default=None),
    preview_token: str | None = Form(default=None),
    note: str | None = Form(default=None),
    form_file: UploadFile | None = File(default=None),
) -> QuoteOut:
    with db_conn() as conn:
        old = conn.execute(
            "SELECT * FROM quote_items WHERE id = ? AND is_delete = 0", (item_id,)
        ).fetchone()
        if old is None:
            raise HTTPException(status_code=404, detail="报价产品明细不存在")
        quote, _deal_row = _assert_editable(conn, old["quote_id"])
        resolved_product_id = int(product_id or old["product_id"])
        product = get_product(conn, resolved_product_id, active_only=True)
        if product is None:
            raise ApiError(400, "product_not_found", "关联产品不存在或已停用")
        snapshot = product_snapshot(product)
        form_key = old["form_storage_key"]
        form_name = old["form_file_name"]
        form_size = old["form_file_size"]
        form_mime = old["form_mime_type"]
        form_sha = old["form_sha256"]
        form_content = old["form_content_json"]
        recognized_total = old["recognized_total"]
        a1_value = old["a1_value"]
        amount_cell = old["amount_cell"]
        preview_key = old["form_preview_storage_key"]
        if form_file is not None and form_file.filename:
            filename, data = await _read_xlsx(form_file)
            inspected = _inspect_upload(product, filename, data)
            if not preview_token or inspected["preview_token"] != preview_token:
                raise ApiError(
                    409,
                    "quote_form_preview_stale",
                    "下单表在预览后发生变化，请重新识别",
                )
            recognized_total = round(float(inspected["recognized_total"]), 2)
            form_key, form_sha = _store_form(filename, data)
            form_name, form_size = filename, len(data)
            form_mime = DOC_MIME_BY_EXT[".xlsx"]
            form_content = json.dumps(
                {
                    "filename": filename,
                    "sheets": [inspected["sheet_content"]],
                    "sheet_count": 1,
                },
                ensure_ascii=False,
            )
            a1_value = inspected["a1_value"]
            amount_cell = inspected["amount_cell"]
            preview_key = inspected["preview_storage_key"]
        elif resolved_product_id != int(old["product_id"]):
            raise ApiError(
                400,
                "quote_form_required_for_product_change",
                "更换关联产品时必须重新上传并识别对应下单表",
            )
        conn.execute(
            "UPDATE quote_items SET product_id = ?, product_code_snapshot = ?,"
            " product_name_snapshot = ?, product_config_snapshot = ?, product_type = ?,"
            " model = ?, drive_type = ?, quantity = 1, unit_price = ?, amount = ?,"
            " note = ?, form_storage_key = ?, form_file_name = ?, form_file_size = ?,"
            " form_mime_type = ?, form_sha256 = ?, form_content_json = ?,"
            " recognized_total = ?, a1_value = ?, amount_cell = ?,"
            " form_preview_storage_key = ?, updated_at = ? WHERE id = ?",
            (
                resolved_product_id,
                snapshot["product_code_snapshot"],
                snapshot["product_name_snapshot"],
                snapshot["product_config_snapshot"],
                snapshot["product_type"],
                snapshot["model"],
                snapshot["drive_type"],
                recognized_total,
                recognized_total,
                ((note or "").strip() or None) if note is not None else old["note"],
                form_key,
                form_name,
                form_size,
                form_mime,
                form_sha,
                form_content,
                recognized_total,
                a1_value,
                amount_cell,
                preview_key,
                now_iso(),
                item_id,
            ),
        )
        total = _sync_amount(conn, old["quote_id"])
        add_entry(
            conn,
            object_type="deal",
            object_id=quote["deal_id"],
            kind="quote",
            customer_id=quote["customer_id"],
            deal_id=quote["deal_id"],
            quote_id=old["quote_id"],
            content=f"修改报价单 {quote['quote_no']} 的产品明细",
            detail={"quote_id": old["quote_id"], "amount": total},
        )
        return _quote_out(conn, _quote(conn, old["quote_id"]))


@router.delete("/quotes/items/{item_id}", response_model=QuoteOut)
def delete_quote_item(item_id: int) -> QuoteOut:
    with db_conn() as conn:
        old = conn.execute(
            "SELECT * FROM quote_items WHERE id = ? AND is_delete = 0", (item_id,)
        ).fetchone()
        if old is None:
            raise HTTPException(status_code=404, detail="报价产品明细不存在")
        quote, _ = _assert_editable(conn, old["quote_id"])
        conn.execute(
            "UPDATE quote_items SET is_delete = 1, updated_at = ? WHERE id = ?",
            (now_iso(), item_id),
        )
        total = _sync_amount(conn, old["quote_id"])
        add_entry(
            conn,
            object_type="deal",
            object_id=quote["deal_id"],
            kind="quote",
            customer_id=quote["customer_id"],
            deal_id=quote["deal_id"],
            quote_id=old["quote_id"],
            content=f"报价单 {quote['quote_no']} 删除产品明细",
            detail={"quote_id": old["quote_id"], "amount": total},
        )
        return _quote_out(conn, _quote(conn, old["quote_id"]))


async def _save_confirmation_files(conn, quote_id: int, screenshots) -> list[int]:
    ids: list[int] = []
    for upload in screenshots or []:
        data = await upload.read()
        if not data:
            continue
        if len(data) > MAX_FILE_BYTES:
            raise ApiError(400, "quote_confirmation_too_large", "确认截图不能超过 20MB")
        filename = Path(upload.filename or "确认截图").name
        ext, mime = ext_and_mime(filename, upload.content_type)
        key = new_storage_key(ext)
        save_photo(key, data)
        cur = conn.execute(
            "INSERT INTO attachments"
            " (object_type, object_id, storage_key, file_name, mime_type, size, created_at)"
            " VALUES ('quote_confirmation', ?, ?, ?, ?, ?, ?)",
            (quote_id, key, filename, mime, len(data), now_iso()),
        )
        ids.append(int(cur.lastrowid or 0))
    return ids


@router.post("/quotes/{quote_id}/confirm", response_model=QuoteOut)
async def confirm_quote(
    quote_id: int,
    note: str | None = Form(default=None),
    screenshots: list[UploadFile] = File(default=[]),
) -> QuoteOut:
    with db_conn() as conn:
        quote, deal = _assert_editable(conn, quote_id)
        items = _quote_items(conn, quote_id)
        if not items:
            raise ApiError(409, "quote_item_required", "报价单没有产品，不能确认")
        missing = [row["product_name_snapshot"] or row["product_code_snapshot"] for row in items
                   if not row["form_storage_key"]]
        if missing:
            raise ApiError(
                409,
                "quote_form_required",
                "以下产品尚未上传下单表：" + "、".join(missing),
            )
        other = conn.execute(
            "SELECT quote_no FROM deal_quotes WHERE deal_id = ?"
            " AND status = 'confirmed' AND is_delete = 0 AND id <> ?",
            (deal["id"], quote_id),
        ).fetchone()
        if other:
            raise ApiError(
                409,
                "quote_already_confirmed",
                f"该商机已有客户确认的报价单 {other['quote_no']}",
            )
        await _save_confirmation_files(conn, quote_id, screenshots)
        now = now_iso()
        amount = _sync_amount(conn, quote_id)
        conn.execute(
            "UPDATE deal_quotes SET status = 'confirmed', confirmed_at = ?,"
            " confirmation_note = ?, updated_at = ? WHERE id = ?",
            (now, (note or "").strip() or None, now, quote_id),
        )
        conn.execute(
            "UPDATE deals SET stage = 'won', closed_at = COALESCE(closed_at, ?),"
            " amount = ?, updated_at = ? WHERE id = ?",
            (now_local_iso(), amount, now, deal["id"]),
        )
        add_entry(
            conn,
            object_type="deal",
            object_id=deal["id"],
            kind="confirm",
            customer_id=deal["customer_id"],
            deal_id=deal["id"],
            quote_id=quote_id,
            content=(
                f"客户已确认报价单 {quote['quote_no']}，报价 ¥{amount:,.2f}"
                + (f"；{(note or '').strip()}" if (note or "").strip() else "")
            ),
            detail={"quote_id": quote_id, "amount": amount},
        )
        return _quote_out(conn, _quote(conn, quote_id))


@router.post("/quotes/{quote_id}/orders", response_model=dict)
def create_order_from_quote(quote_id: int, payload: dict) -> dict:
    from app.routers.deals import _create_order

    with db_conn() as conn:
        quote = _quote(conn, quote_id)
        if quote["status"] != "confirmed":
            raise ApiError(409, "quote_not_confirmed", "客户确认报价单后才能生成订单")
        deal_row, order_row = _create_order(
            conn,
            quote["deal_id"],
            payload,
            quote_id=quote_id,
        )
        timeline = entries_for(
            conn,
            object_type="deal",
            object_id=quote["deal_id"],
            include_order_events=True,
        )
        return {
            "quote": _quote_out(conn, _quote(conn, quote_id)).model_dump(),
            "deal": deal_row,
            "order": order_row,
            "timeline": timeline,
        }


@router.get("/quotes/items/{item_id}/form")
def download_quote_form(item_id: int) -> FileResponse:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT form_storage_key, form_file_name, form_mime_type"
            " FROM quote_items WHERE id = ? AND is_delete = 0",
            (item_id,),
        ).fetchone()
    if row is None or not row["form_storage_key"]:
        raise HTTPException(status_code=404, detail="下单表不存在")
    path = resolve_upload_path(row["form_storage_key"])
    return FileResponse(
        path,
        media_type=row["form_mime_type"] or DOC_MIME_BY_EXT[".xlsx"],
        filename=row["form_file_name"] or path.name,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/quotes/form-previews/{token}")
def get_form_preview(token: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise HTTPException(status_code=404, detail="下单表预览不存在")
    path = resolve_upload_path(f"quote-previews/{token}.png")
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/quotes/items/{item_id}/form-preview")
def get_saved_form_preview(item_id: int) -> FileResponse:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT form_preview_storage_key FROM quote_items"
            " WHERE id = ? AND is_delete = 0",
            (item_id,),
        ).fetchone()
    if row is None or not row["form_preview_storage_key"]:
        raise HTTPException(status_code=404, detail="下单表预览不存在")
    path = resolve_upload_path(row["form_preview_storage_key"])
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/quotes/items/{item_id}/template")
def download_product_template(item_id: int) -> FileResponse:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT p.form_storage_key, p.form_file_name FROM quote_items q"
            " JOIN products p ON p.id = q.product_id"
            " WHERE q.id = ? AND q.is_delete = 0 AND p.is_delete = 0",
            (item_id,),
        ).fetchone()
    if row is None or not row["form_storage_key"]:
        raise HTTPException(status_code=404, detail="产品模板不存在")
    path = resolve_upload_path(row["form_storage_key"])
    return FileResponse(
        path,
        media_type=DOC_MIME_BY_EXT[".xlsx"],
        filename=row["form_file_name"] or path.name,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, max-age=86400"},
    )
