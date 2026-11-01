"""读取、校验并渲染报价单上传的 Excel 下单表。"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


MAX_ROWS = 160
MAX_COLS = 48
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024


class QuoteFormParseError(ValueError):
    """上传的下单表不是可读取或可识别的 .xlsx 文件。"""


def normalize_form_title(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "\u3000"))
    return text.replace("（", "(").replace("）", ")").lower()


def _cell_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").strip()
        text = text.removesuffix("元").strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _validate_xlsx(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise QuoteFormParseError("文件内容不是有效的 Excel 工作簿")
            total = sum(item.file_size for item in archive.infolist())
            if total > MAX_UNCOMPRESSED_BYTES:
                raise QuoteFormParseError("Excel 解压后内容过大，无法展示")
    except zipfile.BadZipFile as exc:
        raise QuoteFormParseError("文件内容不是有效的 Excel 工作簿") from exc


def _load_workbooks(data: bytes):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise QuoteFormParseError("服务端缺少 Excel 解析组件") from exc
    try:
        formula_book = load_workbook(
            io.BytesIO(data), read_only=True, data_only=False, keep_links=False
        )
        value_book = load_workbook(
            io.BytesIO(data), read_only=True, data_only=True, keep_links=False
        )
    except Exception as exc:
        raise QuoteFormParseError("Excel 无法解析，请确认文件未损坏或加密") from exc
    return formula_book, value_book


def read_sheet1_a1(data: bytes) -> str | None:
    formula_book, value_book = _load_workbooks(data)
    try:
        value = value_book.worksheets[0]["A1"].value
        return str(value).strip() if value not in (None, "") else None
    finally:
        formula_book.close()
        value_book.close()


def _extract_total(rows: list[list[Any]]) -> tuple[float | None, str | None]:
    anchors: list[tuple[int, int, str]] = []
    for row_index, row in enumerate(rows, start=1):
        for col_index, value in enumerate(row, start=1):
            if not isinstance(value, str):
                continue
            compact = re.sub(r"\s+", "", value)
            if "合计" in compact or "总金额" in compact or "总计" in compact:
                anchors.append((row_index, col_index, value))

    def pick(candidates):
        for row_index, col_index, value in candidates:
            amount = _number(value)
            if amount is not None and amount > 0:
                return round(amount, 2), f"{row_index}:{col_index}"
        return None, None

    for row_index, col_index, _label in anchors:
        row = rows[row_index - 1]
        amount_cols = []
        for header_row in rows[:row_index]:
            for header_col, value in enumerate(header_row, start=1):
                if (
                    isinstance(value, str)
                    and "金额" in value
                    and "单价" not in value
                    and "合计" not in value
                ):
                    amount_cols.append(header_col)
        amount_col = max(amount_cols, default=None)
        if amount_col:
            candidates = [(row_index, amount_col, row[amount_col - 1])]
            candidates.extend(
                (next_index + 1, amount_col, rows[next_index][amount_col - 1])
                for next_index in range(row_index, min(len(rows), row_index + 8))
                if amount_col - 1 < len(rows[next_index])
            )
            amount, loc = pick(candidates)
            if amount is not None:
                return amount, loc
        amount, loc = pick(
            [
                (row_index, index + 1, value)
                for index, value in enumerate(row[col_index:], start=col_index)
            ]
        )
        if amount is not None:
            return amount, loc
        for next_index in range(row_index, min(len(rows), row_index + 8)):
            amount, loc = pick(
                [
                    (next_index + 1, index + 1, value)
                    for index, value in enumerate(rows[next_index])
                ]
            )
            if amount is not None:
                return amount, loc
    return None, None


def _render_data_area_png(rows: list[list[Any]]) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise QuoteFormParseError("服务端缺少图片生成组件 Pillow") from exc

    font = None
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ):
        if candidate.is_file():
            try:
                font = ImageFont.truetype(str(candidate), 14)
                break
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    col_count = max((len(row) for row in rows), default=0)
    if not rows or not col_count:
        raise QuoteFormParseError("Sheet1 没有可保存的数据区域")

    widths = []
    for col in range(col_count):
        longest = 0
        for row in rows:
            value = row[col] if col < len(row) else ""
            text = "" if value is None else str(value)
            longest = max(longest, max((len(line) for line in text.splitlines()), default=0))
        widths.append(min(320, max(88, 22 + longest * 8)))
    row_height = 30
    width = sum(widths) + 20
    height = len(rows) * row_height + 20
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)

    x = 10
    for col, col_width in enumerate(widths):
        y = 10
        for row in rows:
            value = row[col] if col < len(row) else ""
            text = "" if value is None else str(value)
            draw.rectangle(
                (x, y, x + col_width, y + row_height),
                outline="#d9e1ea",
                fill="#f8fafc" if value not in (None, "") else "#ffffff",
            )
            if text:
                draw.text((x + 5, y + 7), text[:160], fill="#1d2939", font=font)
            y += row_height
        x += col_width

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def inspect_excel_form(data: bytes, filename: str) -> dict:
    """只使用 Sheet1，返回 A1、金额和渲染图片。"""
    if Path(filename).suffix.lower() != ".xlsx":
        raise QuoteFormParseError("下单表请使用 .xlsx；旧版 .xls 请先另存为 .xlsx")
    _validate_xlsx(data)
    formula_book, value_book = _load_workbooks(data)
    try:
        formula_sheet = formula_book.worksheets[0]
        value_sheet = value_book.worksheets[0]
        source_rows = min(int(formula_sheet.max_row or 0), MAX_ROWS)
        source_cols = min(int(formula_sheet.max_column or 0), MAX_COLS)
        rows: list[list[str | int | float | bool | None]] = []
        for row_number, row in enumerate(formula_sheet.iter_rows(
            min_row=1, max_row=source_rows, min_col=1, max_col=source_cols
        ), start=1):
            rendered = []
            for column_number, cell in enumerate(row, start=1):
                cached = value_sheet.cell(row_number, column_number).value
                rendered.append(_cell_value(cached if cached is not None else cell.value))
            rows.append(rendered)
        while rows and not any(value not in (None, "") for value in rows[-1]):
            rows.pop()
        last_col = 0
        for row in rows:
            for index, value in enumerate(row, start=1):
                if value not in (None, ""):
                    last_col = max(last_col, index)
        rows = [row[:last_col] for row in rows]
        a1_value = value_sheet["A1"].value
        a1_value = str(a1_value).strip() if a1_value not in (None, "") else None
    finally:
        formula_book.close()
        value_book.close()

    amount, amount_cell = _extract_total(rows)
    if amount is None:
        raise QuoteFormParseError("未在 Sheet1 中识别到大于 0 的合计金额")
    image_bytes = _render_data_area_png(rows)
    return {
        "filename": Path(filename).name,
        "a1_value": a1_value,
        "recognized_total": amount,
        "amount_cell": amount_cell,
        "sheet_content": {
            "name": "Sheet1",
            "rows": rows,
            "row_count": len(rows),
            "column_count": last_col,
        },
        "image_bytes": image_bytes,
    }
