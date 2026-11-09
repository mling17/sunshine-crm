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


_RECEIVER_LABEL_RE = re.compile(
    r"^\s*(?:收(?:货|件)人|联系人)\s*(?:[+＋]\s*电话)?\s*[：:]?\s*"
)
_MOBILE_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?86[-\s]?)?1[3-9](?:[-\s]?\d){9}(?!\d)"
)
_LANDLINE_PHONE_RE = re.compile(
    r"(?<!\d)(?:0\d{2,3}[-\s]?\d{7,8})(?!\d)"
)


def _text_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def extract_shipping_recipient(
    rows: list[list[Any]],
) -> dict[str, str] | None:
    """从 Sheet1 的 A2（兼容 A1）和 B3 提取单个收货人快照。"""

    def cell(row_number: int, column_number: int) -> str:
        if row_number < 1 or row_number > len(rows):
            return ""
        row = rows[row_number - 1]
        if column_number < 1 or column_number > len(row):
            return ""
        return _text_value(row[column_number - 1])

    address = cell(3, 2)
    if not address:
        return None

    for row_number, cell_name in ((2, "A2"), (1, "A1")):
        receiver_line = cell(row_number, 1)
        if not receiver_line:
            continue
        phone_match = _MOBILE_PHONE_RE.search(receiver_line)
        if phone_match is None:
            phone_match = _LANDLINE_PHONE_RE.search(receiver_line)
        if phone_match is None:
            continue

        phone_digits = re.sub(r"\D", "", phone_match.group(0))
        if len(phone_digits) == 13 and phone_digits.startswith("86"):
            phone_digits = phone_digits[2:]
        if len(phone_digits) < 7:
            continue

        name = _RECEIVER_LABEL_RE.sub("", receiver_line[: phone_match.start()])
        name = name.strip(" \t,，;；/、-")
        if not name:
            continue
        return {
            "receiver_name": name,
            "receiver_phone": phone_digits,
            "receiver_address": address,
            "source_cells": f"Sheet1!{cell_name}，Sheet1!B3",
        }
    return None


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
            io.BytesIO(data), read_only=False, data_only=False, keep_links=False
        )
        value_book = load_workbook(
            io.BytesIO(data), read_only=False, data_only=True, keep_links=False
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


def read_sheet1_shipping_recipient(data: bytes) -> dict[str, str] | None:
    """直接读取上传版本的下单表，提取 A2/A1 与 B3 收货信息。"""
    formula_book, value_book = _load_workbooks(data)
    try:
        value_sheet = value_book.worksheets[0]
        rows = [
            [value_sheet.cell(row_number, column_number).value
             for column_number in (1, 2)]
            for row_number in (1, 2, 3)
        ]
        return extract_shipping_recipient(rows)
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


def _color(value: Any, default: str) -> str:
    rgb = getattr(value, "rgb", None)
    if isinstance(rgb, str) and len(rgb) == 8:
        return "#" + rgb[-6:]
    return default


def _display_value(value: Any, number_format: str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fmt = (number_format or "").lower()
        if "%" in fmt:
            decimals = 2 if "0.00" in fmt else 0
            return f"{float(value) * 100:.{decimals}f}%"
        if "¥" in fmt or "￥" in fmt or "cny" in fmt:
            return f"¥{float(value):,.2f}"
        if "#,##0.00" in fmt:
            return f"{float(value):,.2f}"
        if "#,##0" in fmt:
            return f"{float(value):,.0f}"
    return str(value)


def _font_candidates() -> list[Path]:
    return [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def _wrap_text(value: str, font, max_width: int) -> list[str]:
    from PIL import ImageFont

    if not value:
        return [""]
    lines: list[str] = []
    for paragraph in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            box = font.getbbox(candidate) if hasattr(font, "getbbox") else ImageFont
            width = box[2] - box[0] if isinstance(box, tuple) else len(candidate) * 8
            if current and width > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines or [""]


def _render_data_area_png(worksheet, value_worksheet, rows: list[list[Any]]) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise QuoteFormParseError("服务端缺少图片生成组件 Pillow") from exc

    font_path = None
    for candidate in _font_candidates():
        if candidate.is_file():
            font_path = str(candidate)
            break
    font_cache = {}

    def get_font(cell_font):
        size = max(9, min(24, round(float(cell_font.sz or 11) * 96 / 72)))
        key = (size, bool(cell_font.bold), bool(cell_font.italic))
        if key not in font_cache:
            if font_path:
                try:
                    font_cache[key] = ImageFont.truetype(font_path, size)
                except OSError:
                    font_cache[key] = ImageFont.load_default()
            else:
                font_cache[key] = ImageFont.load_default()
        return font_cache[key]

    col_count = max((len(row) for row in rows), default=0)
    if not rows or not col_count:
        raise QuoteFormParseError("Sheet1 没有可保存的数据区域")

    from openpyxl.utils import get_column_letter
    from openpyxl.utils.cell import range_boundaries

    widths = []
    for col in range(1, col_count + 1):
        dim = worksheet.column_dimensions.get(get_column_letter(col))
        excel_width = float(dim.width) if dim and dim.width else 8.43
        widths.append(max(40, min(420, int(excel_width * 7 + 5))))
    heights = []
    for row_index in range(1, len(rows) + 1):
        dim = worksheet.row_dimensions.get(row_index)
        points = float(dim.height) if dim and dim.height else 15
        heights.append(max(22, min(160, int(points * 96 / 72))))

    merged_anchors = {}
    covered = set()
    merged_ranges = list(worksheet.merged_cells.ranges)
    for merged in merged_ranges:
        min_col, min_row, max_col, max_row = range_boundaries(str(merged))
        if min_row < 1 or min_col < 1 or min_row > len(rows) or min_col > col_count:
            continue
        merged_anchors[(min_row, min_col)] = (max_row, max_col)
        for row_index in range(min_row, max_row + 1):
            for col_index in range(min_col, max_col + 1):
                if (row_index, col_index) != (min_row, min_col):
                    covered.add((row_index, col_index))

    width = sum(widths) + 2
    height = sum(heights) + 2
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    y_positions = [1]
    for value in heights:
        y_positions.append(y_positions[-1] + value)
    x_positions = [1]
    for value in widths:
        x_positions.append(x_positions[-1] + value)

    def draw_cell(row_index: int, col_index: int, end_row: int, end_col: int):
        if (row_index, col_index) in covered:
            return
        cell = value_worksheet.cell(row_index, col_index)
        style_cell = worksheet.cell(row_index, col_index)
        x1, x2 = x_positions[col_index - 1], x_positions[min(end_col, col_count)]
        y1, y2 = y_positions[row_index - 1], y_positions[min(end_row, len(rows))]
        fill = _color(style_cell.fill.fgColor, "#ffffff") if style_cell.fill.fill_type else "#ffffff"
        draw.rectangle((x1, y1, x2, y2), fill=fill)

        border = style_cell.border
        border_width = max(
            1,
            min(3, max(
                int(side.style == "medium") + 1 if side and side.style else 0
                for side in (border.left, border.right, border.top, border.bottom)
            )),
        )
        border_color = _color(
            next((side.color for side in (border.left, border.right, border.top, border.bottom)
                  if side and side.color), None),
            "#b8c2cf",
        )
        draw.rectangle((x1, y1, x2, y2), outline=border_color, width=border_width)

        value = cell.value
        if value in (None, ""):
            return
        text = _display_value(value, style_cell.number_format)
        font = get_font(style_cell.font)
        horizontal = style_cell.alignment.horizontal or "general"
        vertical = style_cell.alignment.vertical or "bottom"
        wrapped = _wrap_text(text, font, max(10, x2 - x1 - 8))
        line_boxes = [draw.textbbox((0, 0), line, font=font) for line in wrapped]
        text_height = sum(box[3] - box[1] + 2 for box in line_boxes)
        text_width = max((box[2] - box[0] for box in line_boxes), default=0)
        if horizontal == "center":
            tx = x1 + max(3, (x2 - x1 - text_width) // 2)
        elif horizontal == "right":
            tx = x2 - text_width - 4
        else:
            tx = x1 + 4
        if vertical == "center":
            ty = y1 + max(2, (y2 - y1 - text_height) // 2)
        elif vertical == "top":
            ty = y1 + 3
        else:
            ty = max(y1 + 3, y2 - text_height - 3)
        color = _color(style_cell.font.color, "#1d2939")
        for line in wrapped:
            draw.text((tx, ty), line, fill=color, font=font)
            ty += draw.textbbox((0, 0), line, font=font)[3] + 2

    for row_index in range(1, len(rows) + 1):
        for col_index in range(1, col_count + 1):
            if (row_index, col_index) in covered:
                continue
            end_row, end_col = merged_anchors.get(
                (row_index, col_index), (row_index, col_index)
            )
            draw_cell(
                row_index,
                col_index,
                min(end_row, len(rows)),
                min(end_col, col_count),
            )

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
        amount, amount_cell = _extract_total(rows)
        if amount is None:
            raise QuoteFormParseError("未在 Sheet1 中识别到大于 0 的合计金额")
        image_bytes = _render_data_area_png(formula_sheet, value_sheet, rows)
    finally:
        formula_book.close()
        value_book.close()

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
