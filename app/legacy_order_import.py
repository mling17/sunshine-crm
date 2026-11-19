"""Historical order-form importer for Sunshine CRM.

This module is intentionally separate from the HTTP routers: importing legacy
workbooks creates the whole customer/deal/quote/order chain in one transaction
and must support a dry-run without mutating business data.

Confirmed product rule: `Sheet1!A1` is the product title and must match one
non-deleted product name after whitespace/full-width normalization.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from app.db import db_conn
from app.product_catalog import config_summary, parse_attributes
from app.security import now_iso, now_local_iso
from app.services import next_no
from app.storage import DOC_MIME_BY_EXT, new_storage_key, save_photo
from app.timeline import add_entry


DEFAULT_OWNER = "刘晓寒"
IMPORT_TAG = "历史订单导入"
DEFAULT_ERROR_DIR = Path(r"C:\Users\P0182449\Desktop\import_error")
DEFAULT_MANIFEST = Path(r"C:\Users\P0182449\Desktop\legacy_order_import_manifest.json")


class ImportParseError(ValueError):
    """A source workbook cannot be safely turned into an order."""

    def __init__(self, code: str, message: str, cell: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.cell = cell


@dataclass
class ParsedOrder:
    source_path: Path
    a1: str
    product_id: int
    product_code: str
    product_name: str
    product_type: str | None
    product_model: str | None
    product_drive_type: str | None
    product_config: str
    product_snapshot: dict[str, Any]
    order_date: date
    completed_date: date
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    amount: float
    quantity: int
    unit_price: float
    spec: str
    production_spec: str
    owner: str
    amount_cell: str
    sha256: str


@dataclass
class RunResult:
    source: str
    dry_run: bool
    recursive: bool
    run_dir: str
    scanned: int = 0
    imported: int = 0
    planned: int = 0
    failed: int = 0
    ignored: int = 0
    duplicate_customer_phones: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "dry_run": self.dry_run,
            "recursive": self.recursive,
            "run_dir": self.run_dir,
            "scanned": self.scanned,
            "imported": self.imported,
            "planned": self.planned,
            "failed": self.failed,
            "ignored": self.ignored,
            "duplicate_customer_phones": self.duplicate_customer_phones,
            "files": self.files,
            "errors": self.errors,
        }


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", text).lower()


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    match = re.search(r"1[3-9]\d{9}", digits)
    return match.group(0) if match else ""


def _clean_name(value: str) -> str:
    text = value or ""
    for label in (
        "收货人+电话", "收货人", "收货单位", "联系人", "联系电话",
        "电话", "手机号", "手机", "收货信息",
    ):
        text = text.replace(label, "")
    text = re.sub(r"\d", "", text)
    text = re.sub(r"[：:，,。；;+()（）\s\-]+", "", text)
    return text.strip()


def _phone_from_text(text: str) -> str:
    return normalize_phone(text)


def _value_after_label(text: str, label: str) -> str:
    index = text.find(label)
    if index < 0:
        return ""
    value = text[index + len(label):]
    return value.lstrip("：: ").strip()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _is_numbered_row(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value).is_integer() and float(value) > 0
    return bool(re.fullmatch(r"\s*\d+\s*", str(value)))


def _parse_date(value: Any, fallback_year: int | None = None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _cell_text(value)
    if not text:
        return None
    patterns = (
        r"(?P<y>20\d{2})\s*[年./-]\s*(?P<m>\d{1,2})\s*[月./-]\s*(?P<d>\d{1,2})\s*日?",
        r"(?P<y>\d{2})\s*[年./-]\s*(?P<m>\d{1,2})\s*[月./-]\s*(?P<d>\d{1,2})\s*日?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year = int(match.group("y"))
            if year < 100:
                year += 2000
            try:
                return date(year, int(match.group("m")), int(match.group("d")))
            except ValueError:
                return None
    if fallback_year:
        match = re.search(r"(?P<m>\d{1,2})\s*[月./-]\s*(?P<d>\d{1,2})\s*日?", text)
        if match:
            try:
                return date(fallback_year, int(match.group("m")), int(match.group("d")))
            except ValueError:
                return None
    return None


def _filename_date(path: Path) -> date | None:
    match = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", path.stem)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    match = re.search(r"(?<!\d)(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)", path.stem)
    if match:
        try:
            return date(2000 + int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def _iter_text_cells(ws, max_rows: int = 60) -> Iterable[tuple[str, str, int, int]]:
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, max_rows), max_col=ws.max_column):
        for cell in row:
            text = _cell_text(cell.value)
            if text:
                yield text, cell.coordinate, cell.row, cell.column


def _find_label_value(ws, labels: tuple[str, ...], *, max_rows: int = 40) -> tuple[str, str | None]:
    cells = list(_iter_text_cells(ws, max_rows=max_rows))
    for text, coord, row, col in cells:
        if not any(label in text for label in labels):
            continue
        direct = ""
        for label in labels:
            if label in text:
                direct = _value_after_label(text, label)
                if direct:
                    break
        if direct:
            return direct, coord
        for offset in range(1, 7):
            if col + offset > ws.max_column:
                break
            adjacent = _cell_text(ws.cell(row, col + offset).value)
            if adjacent:
                return adjacent, ws.cell(row, col + offset).coordinate
        for offset in range(1, 3):
            if row + offset > ws.max_row:
                break
            adjacent = _cell_text(ws.cell(row + offset, col).value)
            if adjacent:
                return adjacent, ws.cell(row + offset, col).coordinate
    return "", None


def _extract_receiver(ws) -> tuple[str, str, str | None]:
    cells = list(_iter_text_cells(ws, max_rows=12))
    receiver_unit = ""
    for text, _coord, _row, _col in cells:
        if "收货单位" in text or "收货人" in text:
            candidate = _value_after_label(text, "收货单位") or _value_after_label(text, "收货人")
            candidate = _clean_name(candidate)
            if candidate:
                receiver_unit = candidate
                break

    candidates: list[tuple[int, str, str, str | None]] = []
    for text, coord, row, col in cells:
        if not any(label in text for label in ("收货人", "收货单位", "联系人", "联系电话", "电话")):
            continue
        combined = text
        if not _phone_from_text(combined):
            for offset in range(1, 6):
                if col + offset > ws.max_column:
                    break
                adjacent = _cell_text(ws.cell(row, col + offset).value)
                if adjacent:
                    combined += " " + adjacent
                    break
        phone = _phone_from_text(combined)
        if not phone:
            continue
        name = _clean_name(combined.replace(phone, ""))
        if not name:
            name = receiver_unit
        if not name:
            continue
        candidates.append((row, name, phone, coord))

    if not candidates:
        for text, coord, row, col in cells:
            if row > 6:
                continue
            phone = _phone_from_text(text)
            if phone:
                name = receiver_unit or _clean_name(text.replace(phone, ""))
                if name:
                    candidates.append((row + 20, name, phone, coord))
                    break

    if not candidates:
        raise ImportParseError("receiver_missing", "未找到有效的收货人手机号")

    candidates.sort(key=lambda item: item[0])
    _row, name, phone, coord = candidates[0]
    return name, phone, coord


def _extract_address(ws) -> tuple[str, str | None]:
    value, coord = _find_label_value(ws, ("收货地址", "收货信息"), max_rows=40)
    if not value:
        raise ImportParseError("address_missing", "未找到收货地址")
    return value, coord


def _extract_order_date(ws, source_path: Path) -> tuple[date, str | None]:
    value, coord = _find_label_value(ws, ("下单日期",), max_rows=20)
    fallback = _filename_date(source_path)
    parsed = _parse_date(value, fallback_year=fallback.year if fallback else None)
    if parsed is None:
        parsed = fallback
    if parsed is None:
        raise ImportParseError("order_date_missing", "未找到可解析的下单日期", coord)
    return parsed, coord


def _extract_completed_date(ws, order_date: date) -> date:
    value, _coord = _find_label_value(ws, ("出货日期", "生产周期", "交期"), max_rows=20)
    if not value:
        return order_date
    parsed = _parse_date(value, fallback_year=order_date.year)
    if parsed is None:
        return order_date
    if parsed < order_date - timedelta(days=60):
        try:
            return parsed.replace(year=parsed.year + 1)
        except ValueError:
            return order_date
    return parsed


def _header_columns(ws) -> tuple[int | None, dict[str, int]]:
    best_row: int | None = None
    best_map: dict[str, int] = {}
    for row in range(1, min(ws.max_row, 12) + 1):
        mapping: dict[str, int] = {}
        for col in range(1, ws.max_column + 1):
            text = _cell_text(ws.cell(row, col).value)
            if "序号" in text:
                mapping["seq"] = col
            elif "数量" in text:
                mapping["quantity"] = col
            elif "单价" in text:
                mapping["unit_price"] = col
            elif "金额" in text and "合计" not in text:
                mapping["amount"] = col
            elif "产品名称" in text or "品名" in text:
                mapping["name"] = col
        if "quantity" in mapping or "amount" in mapping:
            if not best_map or len(mapping) > len(best_map):
                best_row, best_map = row, mapping
    return best_row, best_map


def _numbered_rows(ws, header_row: int | None) -> list[int]:
    start = (header_row or 1) + 1
    return [row for row in range(start, ws.max_row + 1) if _is_numbered_row(ws.cell(row, 1).value)]


def _row_has_label(ws, row: int, labels: tuple[str, ...]) -> bool:
    return any(any(label in _cell_text(ws.cell(row, col).value) for label in labels)
               for col in range(1, ws.max_column + 1))


def _extract_total(ws, header_row: int | None, columns: dict[str, int]) -> tuple[float, str]:
    # Prefer the explicit 合计 row. Payment rows below it (定金/尾款) must not
    # be mistaken for the order total.
    for row in range(1, ws.max_row + 1):
        if not _row_has_label(ws, row, ("合计", "总金额", "总计")):
            continue
        amount_col = columns.get("amount")
        if amount_col:
            value = _numeric(ws.cell(row, amount_col).value)
            if value is not None and value > 0:
                return round(value, 2), ws.cell(row, amount_col).coordinate
        for col in range(ws.max_column, 0, -1):
            value = _numeric(ws.cell(row, col).value)
            if value is not None and value > 0:
                return round(value, 2), ws.cell(row, col).coordinate
        for next_row in range(row + 1, min(ws.max_row, row + 4) + 1):
            if _row_has_label(ws, next_row, ("定金", "尾款", "收款")):
                break
            if amount_col:
                value = _numeric(ws.cell(next_row, amount_col).value)
                if value is not None and value > 0:
                    return round(value, 2), ws.cell(next_row, amount_col).coordinate
            for col in range(ws.max_column, 0, -1):
                value = _numeric(ws.cell(next_row, col).value)
                if value is not None and value > 0:
                    return round(value, 2), ws.cell(next_row, col).coordinate

    # Some old forms omit the 合计 label. Scan the amount column from top to
    # bottom, but stop once the payment section begins.
    amount_col = columns.get("amount")
    if amount_col:
        candidates: list[tuple[int, float, str]] = []
        start = (header_row or 1) + 1
        for row in range(start, ws.max_row + 1):
            if _row_has_label(ws, row, ("定金", "尾款", "收款")):
                break
            value = _numeric(ws.cell(row, amount_col).value)
            if value is not None and value > 0:
                candidates.append((row, value, ws.cell(row, amount_col).coordinate))
        if candidates:
            _row, value, coord = candidates[-1]
            return round(value, 2), coord
    raise ImportParseError("amount_missing", "未找到订单合计金额")


def _extract_quantity(ws, header_row: int | None, columns: dict[str, int]) -> int:
    qty_col = columns.get("quantity")
    if qty_col:
        total = 0.0
        for row in _numbered_rows(ws, header_row):
            value = _numeric(ws.cell(row, qty_col).value)
            if value and value > 0:
                total += value
        if total > 0:
            return max(1, int(round(total)))
    return 1


def _extract_spec_and_production(ws, header_row: int | None) -> tuple[str, str]:
    numbered = _numbered_rows(ws, header_row)
    if not numbered:
        return "", "原始下单表见附件"
    start = numbered[0]
    later = [row for row in numbered if row > start]
    end = later[0] - 1 if later else min(ws.max_row, start + 6)
    for row in range(start, min(ws.max_row, start + 12) + 1):
        if _row_has_label(ws, row, ("合计", "定金", "尾款", "备注")):
            end = min(end, row - 1)
            break

    spec = ""
    parts: list[str] = []
    for row in range(start, end + 1):
        label = _cell_text(ws.cell(row, 2).value)
        dim_c = _numeric(ws.cell(row, 3).value)
        dim_d = _numeric(ws.cell(row, 4).value)
        dims = ""
        if dim_c is not None and dim_d is not None:
            dims = f"{dim_c:g}×{dim_d:g}"
        extras: list[str] = []
        for col in range(8, min(ws.max_column, 10) + 1):
            text = _cell_text(ws.cell(row, col).value)
            if text:
                extras.append(text)
        if label or dims or extras:
            segment = label
            if dims:
                segment = f"{segment} {dims}".strip()
            if extras:
                segment = f"{segment}：{' / '.join(extras)}".strip("： ")
            if segment:
                parts.append(segment)
        if dims and ("框制作尺寸" in label or "制作尺寸" in label) and not spec:
            spec = f"{label} {dims}".strip()
        if dims and "洞口尺寸" in label and not spec:
            spec = f"{label} {dims}".strip()

    extra_parts: list[str] = []
    for text, _coord, _row, _col in _iter_text_cells(ws, max_rows=min(ws.max_row, 60)):
        if len(text) > 180:
            continue
        if text.startswith(("颜色", "气撑", "电机", "具体要求", "客户要求")):
            extra_parts.append(text)
    if extra_parts:
        parts.extend(extra_parts)
    production = "；".join(dict.fromkeys(parts))
    return spec[:200], (production or "原始下单表见附件")[:1000]


def _extract_owner(ws) -> str:
    value, _coord = _find_label_value(ws, ("销售员",), max_rows=ws.max_row)
    name = _clean_name(value)
    return name or DEFAULT_OWNER


def _load_products(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM products WHERE is_delete = 0 ORDER BY id").fetchall()
    products = []
    for row in rows:
        data = dict(row)
        data["attributes"] = parse_attributes(data.get("attributes"))
        products.append(data)
    return products


def _match_product(products: list[dict[str, Any]], a1: str) -> dict[str, Any]:
    target = normalize_text(a1)
    if not target:
        raise ImportParseError("a1_missing", "Sheet1!A1 为空，无法匹配产品", "A1")
    matches = [product for product in products if normalize_text(product.get("name")) == target]
    if not matches:
        raise ImportParseError("product_not_found", f"A1 未匹配到产品：{a1}", "A1")
    if len(matches) > 1:
        codes = ", ".join(str(item.get("code") or item.get("id")) for item in matches)
        raise ImportParseError("product_ambiguous", f"A1 匹配到多个产品：{codes}", "A1")
    return matches[0]


def parse_workbook(path: Path, products: list[dict[str, Any]]) -> ParsedOrder:
    try:
        wb = load_workbook(path, data_only=True, read_only=False, keep_links=False)
    except Exception as exc:
        raise ImportParseError("workbook_unreadable", f"Excel 无法读取：{type(exc).__name__}") from exc
    try:
        if not wb.worksheets:
            raise ImportParseError("sheet_missing", "工作簿没有工作表")
        ws = wb.worksheets[0]
        a1 = _cell_text(ws["A1"].value)
        product = _match_product(products, a1)
        order_date, _date_coord = _extract_order_date(ws, path)
        completed_date = _extract_completed_date(ws, order_date)
        receiver_name, receiver_phone, _phone_coord = _extract_receiver(ws)
        receiver_address, _address_coord = _extract_address(ws)
        header_row, columns = _header_columns(ws)
        amount, amount_cell = _extract_total(ws, header_row, columns)
        quantity = _extract_quantity(ws, header_row, columns)
        unit_price = round(amount / max(quantity, 1), 2)
        spec, production_spec = _extract_spec_and_production(ws, header_row)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return ParsedOrder(
            source_path=path,
            a1=a1,
            product_id=int(product["id"]),
            product_code=str(product.get("code") or ""),
            product_name=str(product.get("name") or ""),
            product_type=product.get("category"),
            product_model=product.get("code"),
            product_drive_type=product.get("drive_type"),
            product_config=config_summary(product),
            product_snapshot={
                "product_id": int(product["id"]),
                "product_code_snapshot": product.get("code"),
                "product_name_snapshot": product.get("name"),
                "product_config_snapshot": config_summary(product),
                "product_type": product.get("category"),
                "model": product.get("code"),
                "drive_type": product.get("drive_type"),
            },
            order_date=order_date,
            completed_date=completed_date,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            receiver_address=receiver_address,
            amount=amount,
            quantity=quantity,
            unit_price=unit_price,
            spec=spec,
            production_spec=production_spec,
            owner=_extract_owner(ws),
            amount_cell=amount_cell,
            sha256=sha,
        )
    finally:
        wb.close()


def _iso_date(value: date) -> str:
    return f"{value.isoformat()}T00:00:00"


def _duplicate_customer_phones(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, phone FROM customers WHERE is_delete = 0 ORDER BY id"
    ).fetchall()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        phone = normalize_phone(row["phone"])
        if phone:
            groups[phone].append({"id": int(row["id"]), "name": row["name"]})
    return [
        {"phone": phone, "customers": customers}
        for phone, customers in groups.items()
        if len(customers) > 1
    ]


def _find_customer(conn, phone: str):
    rows = conn.execute(
        "SELECT * FROM customers WHERE is_delete = 0 ORDER BY id"
    ).fetchall()
    matches = [row for row in rows if normalize_phone(row["phone"]) == phone]
    if len(matches) > 1:
        raise ImportParseError("duplicate_customer", f"系统存在多个同手机号客户：{phone}")
    return matches[0] if matches else None


def _find_active_lead(conn, phone: str):
    rows = conn.execute(
        "SELECT * FROM leads WHERE is_delete = 0 AND status IN ('new', 'following') ORDER BY id"
    ).fetchall()
    matches = [row for row in rows if normalize_phone(row["phone"]) == phone]
    if len(matches) > 1:
        raise ImportParseError("duplicate_lead", f"系统存在多条同手机号有效线索：{phone}")
    return matches[0] if matches else None


def _ensure_import_tag(conn) -> int:
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (IMPORT_TAG,)).fetchone()
    if row:
        tag_id = int(row["id"])
        conn.execute(
            "UPDATE tags SET is_delete = 0, update_time = ? WHERE id = ?",
            (now_iso(), tag_id),
        )
        return tag_id
    cur = conn.execute(
        "INSERT INTO tags (name, created_at, create_time, update_time, is_delete)"
        " VALUES (?, ?, ?, ?, 0)",
        (IMPORT_TAG, now_iso(), now_iso(), now_iso()),
    )
    return int(cur.lastrowid or 0)


def _create_customer(conn, parsed: ParsedOrder) -> int:
    now = now_iso()
    created = _iso_date(parsed.order_date)
    cur = conn.execute(
        "INSERT INTO customers (name, phone, customer_type, source, source_other, owner,"
        " created_at, updated_at, create_time, update_time, is_delete)"
        " VALUES (?, ?, 'personal', 'other', ?, ?, ?, ?, ?, ?, 0)",
        (
            parsed.receiver_name,
            parsed.receiver_phone,
            IMPORT_TAG,
            parsed.owner,
            created,
            now,
            now,
            now,
        ),
    )
    return int(cur.lastrowid or 0)


def _create_or_reuse_customer(conn, parsed: ParsedOrder) -> int:
    customer = _find_customer(conn, parsed.receiver_phone)
    if customer is not None:
        return int(customer["id"])
    _find_active_lead(conn, parsed.receiver_phone)
    return _create_customer(conn, parsed)


def _create_deal(conn, customer_id: int, parsed: ParsedOrder) -> int:
    now = now_iso()
    created = _iso_date(parsed.order_date)
    cur = conn.execute(
        "INSERT INTO deals (customer_id, product_type, model, spec, amount, deposit, balance,"
        " stage, closed_at, created_at, updated_at, title, owner, drive_type, product_id,"
        " product_code_snapshot, product_name_snapshot, product_config_snapshot,"
        " create_time, update_time, is_delete)"
        " VALUES (?, ?, ?, ?, ?, ?, 0, 'won', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (
            customer_id,
            parsed.product_type,
            parsed.product_model,
            parsed.spec,
            parsed.amount,
            parsed.amount,
            created,
            created,
            now,
            parsed.product_name,
            parsed.owner,
            parsed.product_drive_type,
            parsed.product_id,
            parsed.product_code,
            parsed.product_name,
            parsed.product_config,
            now,
            now,
        ),
    )
    return int(cur.lastrowid or 0)


def _mark_lead_converted(conn, parsed: ParsedOrder, customer_id: int, deal_id: int) -> None:
    now = now_iso()
    created = _iso_date(parsed.order_date)
    lead = _find_active_lead(conn, parsed.receiver_phone)
    if lead is None:
        cur = conn.execute(
            "INSERT INTO leads (name, phone, lead_type, source, source_other, location, note,"
            " status, owner, created_at, updated_at, create_time, update_time, is_delete)"
            " VALUES (?, ?, 'personal', 'other', ?, NULL, NULL, 'converted', ?, ?, ?, ?, ?, 0)",
            (
                parsed.receiver_name,
                parsed.receiver_phone,
                IMPORT_TAG,
                parsed.owner,
                created,
                now,
                now,
                now,
            ),
        )
        lead_id = int(cur.lastrowid or 0)
    else:
        lead_id = int(lead["id"])
    conn.execute(
        "UPDATE leads SET status = 'converted', converted_customer_id = ?,"
        " converted_deal_id = ?, updated_at = ?, update_time = ? WHERE id = ?",
        (customer_id, deal_id, now, now, lead_id),
    )


def _add_import_tag(conn, deal_id: int) -> None:
    tag_id = _ensure_import_tag(conn)
    row = conn.execute(
        "SELECT id FROM deal_tags WHERE deal_id = ? AND tag_id = ? AND source = 'manual'",
        (deal_id, tag_id),
    ).fetchone()
    now = now_iso()
    if row:
        conn.execute(
            "UPDATE deal_tags SET is_delete = 0, updated_at = ?, update_time = ? WHERE id = ?",
            (now, now, row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO deal_tags (deal_id, tag_id, source, created_at, updated_at,"
            " create_time, update_time, is_delete)"
            " VALUES (?, ?, 'manual', ?, ?, ?, ?, 0)",
            (deal_id, tag_id, now, now, now, now),
        )


def _persist_parsed(conn, parsed: ParsedOrder) -> dict[str, Any]:
    now = now_iso()
    created = _iso_date(parsed.order_date)
    completed = _iso_date(parsed.completed_date)
    customer_id = _create_or_reuse_customer(conn, parsed)
    deal_id = _create_deal(conn, customer_id, parsed)
    _mark_lead_converted(conn, parsed, customer_id, deal_id)
    _add_import_tag(conn, deal_id)

    quote_no = next_no(conn, "deal_quotes", "quote_no", "QT", now_local_iso()[:10])
    cur = conn.execute(
        "INSERT INTO deal_quotes (quote_no, deal_id, customer_id, title, note, status, amount,"
        " confirmed_at, confirmation_note, created_at, updated_at, create_time, update_time, is_delete)"
        " VALUES (?, ?, ?, ?, NULL, 'confirmed', ?, ?, NULL, ?, ?, ?, ?, 0)",
        (quote_no, deal_id, customer_id, parsed.product_name, parsed.amount, created, created, now, now, now),
    )
    quote_id = int(cur.lastrowid or 0)

    key = new_storage_key(".xlsx")
    target = save_photo(key, parsed.source_path.read_bytes())
    try:
        form_content = json.dumps(
            {"filename": parsed.source_path.name, "sheet": "Sheet1", "legacy_import": True},
            ensure_ascii=False,
        )
        cur = conn.execute(
            "INSERT INTO quote_items (quote_id, deal_id, product_id, product_code_snapshot,"
            " product_name_snapshot, product_config_snapshot, product_type, model, drive_type,"
            " quantity, spec, production_spec, unit_price, amount, note, form_storage_key,"
            " form_file_name, form_file_size, form_mime_type, form_sha256, form_content_json,"
            " recognized_total, a1_value, amount_cell, sort, created_at, updated_at,"
            " create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0)",
            (
                quote_id,
                deal_id,
                parsed.product_id,
                parsed.product_code,
                parsed.product_name,
                parsed.product_config,
                parsed.product_type,
                parsed.product_model,
                parsed.product_drive_type,
                parsed.quantity,
                parsed.spec,
                parsed.production_spec,
                parsed.unit_price,
                parsed.amount,
                key,
                parsed.source_path.name,
                parsed.source_path.stat().st_size,
                DOC_MIME_BY_EXT[".xlsx"],
                parsed.sha256,
                form_content,
                parsed.amount,
                parsed.a1,
                parsed.amount_cell,
                created,
                now,
                now,
                now,
            ),
        )
        quote_item_id = int(cur.lastrowid or 0)

        order_no = next_no(conn, "orders", "order_no", "SO", now_local_iso()[:10])
        order_name = f"{parsed.receiver_name} - {parsed.product_name} - {parsed.order_date.isoformat()}"
        cur = conn.execute(
            "INSERT INTO orders (order_no, order_name, customer_id, deal_id, quote_id, product_id,"
            " product_code_snapshot, product_name_snapshot, product_config_snapshot, product_type,"
            " model, spec, amount, product_total, discount_amount, product_payable, deposit_amount,"
            " balance_amount, deposit_paid, balance_paid, receiver_name, receiver_phone, receiver_address,"
            " status, note, owner, shipped_at, completed_at, customer_confirmed_at,"
            " created_at, updated_at, create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 0, ?, 0, ?, ?, ?, 'completed',"
            " NULL, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                order_no,
                order_name,
                customer_id,
                deal_id,
                quote_id,
                parsed.product_id,
                parsed.product_code,
                parsed.product_name,
                parsed.product_config,
                parsed.product_type,
                parsed.product_model,
                parsed.spec,
                parsed.amount,
                parsed.amount,
                parsed.amount,
                parsed.amount,
                parsed.amount,
                parsed.receiver_name,
                parsed.receiver_phone,
                parsed.receiver_address,
                parsed.owner,
                completed,
                completed,
                created,
                created,
                now,
                now,
                now,
            ),
        )
        order_id = int(cur.lastrowid or 0)

        conn.execute(
            "INSERT INTO order_items (order_id, source_quote_item_id, product_id, product_code_snapshot,"
            " product_name_snapshot, product_config_snapshot, product_type, model, drive_type, quantity,"
            " spec, production_spec, unit_price, amount, note, sort, created_at, updated_at,"
            " create_time, update_time, is_delete)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?, 0)",
            (
                order_id,
                quote_item_id,
                parsed.product_id,
                parsed.product_code,
                parsed.product_name,
                parsed.product_config,
                parsed.product_type,
                parsed.product_model,
                parsed.product_drive_type,
                parsed.quantity,
                parsed.spec,
                parsed.production_spec,
                parsed.unit_price,
                parsed.amount,
                created,
                now,
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE deal_quotes SET order_id = ?, updated_at = ? WHERE id = ?",
            (order_id, now, quote_id),
        )
        conn.execute(
            "UPDATE deals SET order_id = ?, locked_at = ?, amount = ?, updated_at = ?,"
            " update_time = ? WHERE id = ?",
            (order_id, now, parsed.amount, now, now, deal_id),
        )
        conn.execute(
            "INSERT INTO order_status_log (order_id, from_status, to_status, deposit_paid,"
            " balance_paid, note, created_at, event_type, create_time, update_time, is_delete)"
            " VALUES (?, NULL, 'completed', ?, 0, ?, ?, 'stage', ?, ?, 0)",
            (order_id, parsed.amount, IMPORT_TAG, completed, now, now),
        )
        conn.execute(
            "INSERT INTO attachments (object_type, object_id, storage_key, file_name, mime_type,"
            " size, created_at, create_time, update_time, is_delete)"
            " VALUES ('order_confirmation', ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                order_id,
                key,
                parsed.source_path.name,
                DOC_MIME_BY_EXT[".xlsx"],
                parsed.source_path.stat().st_size,
                created,
                now,
                now,
            ),
        )
        add_entry(
            conn,
            object_type="deal",
            object_id=deal_id,
            kind="order",
            customer_id=customer_id,
            deal_id=deal_id,
            quote_id=quote_id,
            content=f"历史订单导入，生成订单 {order_no}",
            detail={"order_id": order_id, "order_no": order_no, "source": str(parsed.source_path)},
            created_at=created,
        )
        add_entry(
            conn,
            object_type="order",
            object_id=order_id,
            kind="system",
            customer_id=customer_id,
            deal_id=deal_id,
            quote_id=quote_id,
            content="历史订单导入",
            detail={"sha256": parsed.sha256, "source": str(parsed.source_path)},
            created_at=now,
        )
        return {
            "customer_id": customer_id,
            "deal_id": deal_id,
            "quote_id": quote_id,
            "order_id": order_id,
            "order_no": order_no,
            "quote_no": quote_no,
            "attachment_key": key,
        }
    except BaseException:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"manifest 无法读取：{path}：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise RuntimeError(f"manifest 格式无效：{path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _source_files(source: Path, recursive: bool) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() == ".xlsx" else []
    pattern = "**/*.xlsx" if recursive else "*.xlsx"
    return sorted(path for path in source.glob(pattern) if path.is_file())


def _relative_for_error(path: Path, source: Path) -> Path:
    if source.is_file():
        return Path(path.name)
    try:
        return path.relative_to(source)
    except ValueError:
        return Path(path.name)


def _copy_error(source_file: Path, source_root: Path, run_dir: Path) -> str:
    relative = _relative_for_error(source_file, source_root)
    target = run_dir / "files" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, target)
    return str(target)


def _record_error(
    result: RunResult,
    *,
    source_file: Path,
    source_root: Path,
    code: str,
    message: str,
    sha256: str | None = None,
    cell: str | None = None,
) -> None:
    copied = _copy_error(source_file, source_root, Path(result.run_dir))
    result.failed += 1
    payload = {
        "file": str(source_file),
        "relative_file": str(_relative_for_error(source_file, source_root)),
        "sha256": sha256,
        "code": code,
        "cell": cell,
        "message": message,
        "copied_to": copied,
    }
    result.errors.append(payload)
    result.files.append({"file": str(source_file), "status": "failed", **payload})


def _write_reports(result: RunResult) -> None:
    run_dir = Path(result.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    fields = ("relative_file", "sha256", "code", "cell", "message", "copied_to")
    with (run_dir / "errors.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for error in result.errors:
            writer.writerow({name: error.get(name) or "" for name in fields})
    _write_json(run_dir / "summary.json", result.as_dict())


def run_import(
    source_dir: Path | str,
    *,
    dry_run: bool = True,
    recursive: bool = False,
    error_dir: Path | str = DEFAULT_ERROR_DIR,
    manifest_path: Path | str = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    source = Path(source_dir).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    error_root = Path(error_dir)
    run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S-%f")
    run_dir = error_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(
        source=str(source),
        dry_run=dry_run,
        recursive=recursive,
        run_dir=str(run_dir),
    )
    files = _source_files(source, recursive)
    result.scanned = len(files)
    manifest_file = Path(manifest_path)
    manifest = _load_manifest(manifest_file)
    imported_hashes = {
        str(entry.get("sha256"))
        for entry in manifest.get("entries", [])
        if entry.get("status") == "imported" and entry.get("sha256")
    }
    seen_hashes: set[str] = set()

    with db_conn() as conn:
        products = _load_products(conn)
        duplicate_customers = _duplicate_customer_phones(conn)
    if duplicate_customers:
        result.duplicate_customer_phones = duplicate_customers
        result.errors.append(
            {"code": "duplicate_customer_phones", "message": "系统存在重复手机号客户，整批中止"}
        )
        _write_reports(result)
        return result.as_dict()

    planned_phones: set[str] = set()
    for source_file in files:
        try:
            sha = hashlib.sha256(source_file.read_bytes()).hexdigest()
            if sha in imported_hashes or sha in seen_hashes:
                _record_error(
                    result,
                    source_file=source_file,
                    source_root=source,
                    code="duplicate_sha256",
                    message="该文件已导入或在本批次中重复出现",
                    sha256=sha,
                )
                continue
            parsed = parse_workbook(source_file, products)
            if dry_run:
                if parsed.receiver_phone not in planned_phones:
                    planned_phones.add(parsed.receiver_phone)
                result.planned += 1
                result.files.append(
                    {
                        "file": str(source_file),
                        "status": "planned",
                        "product": parsed.product_name,
                        "order_date": parsed.order_date.isoformat(),
                        "completed_date": parsed.completed_date.isoformat(),
                        "amount": parsed.amount,
                        "quantity": parsed.quantity,
                        "customer": parsed.receiver_name,
                        "phone": parsed.receiver_phone,
                        "sha256": parsed.sha256,
                    }
                )
                seen_hashes.add(sha)
                continue
            with db_conn() as conn:
                duplicate_customers = _duplicate_customer_phones(conn)
                if duplicate_customers:
                    result.duplicate_customer_phones = duplicate_customers
                    result.errors.append(
                        {"code": "duplicate_customer_phones", "message": "系统存在重复手机号客户，整批中止"}
                    )
                    _write_reports(result)
                    return result.as_dict()
                ids = _persist_parsed(conn, parsed)
            result.imported += 1
            seen_hashes.add(sha)
            manifest["entries"].append(
                {
                    "sha256": sha,
                    "status": "imported",
                    "source": str(source_file),
                    "imported_at": now_iso(),
                    "order_date": parsed.order_date.isoformat(),
                    "amount": parsed.amount,
                    **ids,
                }
            )
            _write_json(manifest_file, manifest)
            result.files.append(
                {
                    "file": str(source_file),
                    "status": "imported",
                    "product": parsed.product_name,
                    "amount": parsed.amount,
                    "customer_id": ids["customer_id"],
                    "deal_id": ids["deal_id"],
                    "quote_id": ids["quote_id"],
                    "order_id": ids["order_id"],
                    "order_no": ids["order_no"],
                    "sha256": sha,
                }
            )
        except ImportParseError as exc:
            _record_error(
                result,
                source_file=source_file,
                source_root=source,
                code=exc.code,
                message=exc.message,
                cell=exc.cell,
            )
        except Exception as exc:
            _record_error(
                result,
                source_file=source_file,
                source_root=source,
                code="import_exception",
                message=f"{type(exc).__name__}: {exc}",
            )
    _write_reports(result)
    return result.as_dict()
