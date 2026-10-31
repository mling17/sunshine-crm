"""Product catalog helpers shared by migrations and API routes."""

from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.security import now_iso


CATALOG_PATH = Path(__file__).parent / "data" / "order_form_catalog.json"
PRODUCT_FORMS_PATH = Path(__file__).parent / "data" / "product_forms"


def load_seed_catalog() -> list[dict[str, Any]]:
    """Load the curated, PII-free catalog derived from the order-form titles."""
    if not CATALOG_PATH.exists():
        return []
    rows = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return rows if isinstance(rows, list) else []


def seed_product_catalog(conn: sqlite3.Connection) -> None:
    """Add missing seed products without overwriting user edits or reviving deleted rows."""
    now = now_iso()
    for row in load_seed_catalog():
        form_key = f"product_forms/{row['code']}.xlsx"
        form_target = settings.uploads_path / form_key
        bundled_form = PRODUCT_FORMS_PATH / f"{row['code']}.xlsx"
        if not form_target.is_file() and bundled_form.is_file():
            form_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_form, form_target)
        form_size = bundled_form.stat().st_size if bundled_form.is_file() else int(row.get("form_size") or 0)
        form_hash = row.get("form_sha256")
        if bundled_form.is_file() and not form_hash:
            form_hash = hashlib.sha256(bundled_form.read_bytes()).hexdigest()
        conn.execute(
            """
            INSERT OR IGNORE INTO products (
                seed_key, code, name, category, series, structure, opening_mode,
                drive_type, frame_type, leaf_type, edge_type, leaf_count,
                min_width, max_width, min_height, max_height, attributes,
                source_template, form_storage_key, form_file_name, form_file_size,
                form_sha256, form_uploaded_at, description, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("seed_key"),
                row.get("code"),
                row.get("name"),
                row.get("category") or "天窗",
                row.get("series"),
                row.get("structure"),
                row.get("opening_mode"),
                row.get("drive_type"),
                row.get("frame_type"),
                row.get("leaf_type"),
                row.get("edge_type"),
                row.get("leaf_count"),
                json.dumps(row.get("attributes") or {}, ensure_ascii=False),
                row.get("source_template"),
                form_key,
                row.get("form_filename"),
                form_size,
                form_hash,
                now,
                row.get("description"),
                1 if row.get("is_active", True) else 0,
                now,
                now,
            ),
        )
        # Existing seed rows from v2_008 gain their required workbook on upgrade.
        conn.execute(
            """
            UPDATE products
               SET form_storage_key = ?,
                   form_file_name = ?,
                   form_file_size = ?,
                   form_sha256 = ?,
                   form_uploaded_at = COALESCE(form_uploaded_at, ?),
                   updated_at = ?,
                   update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
             WHERE seed_key = ?
               AND is_delete = 0
               AND (form_storage_key IS NULL OR form_storage_key = '')
            """,
            (
                form_key,
                row.get("form_filename"),
                form_size,
                form_hash,
                now,
                now,
                row.get("seed_key"),
            ),
        )


def parse_attributes(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def config_summary(row: dict[str, Any]) -> str:
    parts = [
        row.get("series") if row.get("series") not in (None, "", "通用") else None,
        row.get("structure") if row.get("structure") not in (None, "", "标准") else None,
        row.get("opening_mode"),
        row.get("frame_type") if row.get("frame_type") not in (None, "", "标准") else None,
        row.get("leaf_type") if row.get("leaf_type") not in (None, "", "标准") else None,
        row.get("edge_type"),
        f"{row['leaf_count']}扇" if row.get("leaf_count") else None,
    ]
    attributes = parse_attributes(row.get("attributes"))
    for key in ("screen", "mesh", "motor_cover", "shade", "handle"):
        if attributes.get(key):
            parts.append(str(attributes[key]))
    other = attributes.get("other")
    if isinstance(other, list):
        parts.extend(str(item) for item in other if item)
    return " / ".join(part for part in parts if part)


def product_snapshot(product: dict[str, Any]) -> dict[str, Any]:
    """Values frozen on a deal so later catalog edits cannot rewrite evidence."""
    return {
        "product_id": int(product["id"]),
        "product_code_snapshot": product.get("code"),
        "product_name_snapshot": product.get("name"),
        "product_config_snapshot": config_summary(product),
        "product_type": product.get("category"),
        "model": product.get("code"),
        "drive_type": product.get("drive_type"),
    }


def get_product(conn: sqlite3.Connection, product_id: int, *, active_only: bool = False) -> dict[str, Any] | None:
    where = "id = ? AND is_delete = 0"
    if active_only:
        where += " AND is_active = 1"
    row = conn.execute(f"SELECT * FROM products WHERE {where}", (product_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["attributes"] = parse_attributes(data.get("attributes"))
    return data
