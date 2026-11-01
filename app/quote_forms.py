"""读取报价单上传的 Excel 下单表，生成可在 CRM 页面展示的结构化快照。"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


MAX_SHEETS = 8
MAX_ROWS = 160
MAX_COLS = 48
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024


class QuoteFormParseError(ValueError):
    """上传的下单表不是可读取的 .xlsx 文件。"""


def _cell_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _validate_xlsx(data: bytes) -> None:
    value_workbook = None
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


def extract_excel_preview(data: bytes, filename: str) -> dict:
    """返回按工作表拆分的单元格矩阵；不修改原文件。"""
    if Path(filename).suffix.lower() != ".xlsx":
        raise QuoteFormParseError("下单表请使用 .xlsx；旧版 .xls 请先另存为 .xlsx")
    _validate_xlsx(data)
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise QuoteFormParseError("服务端缺少 Excel 解析组件") from exc

    try:
        workbook = load_workbook(
            io.BytesIO(data),
            read_only=True,
            data_only=False,
            keep_links=False,
        )
        value_workbook = load_workbook(
            io.BytesIO(data),
            read_only=True,
            data_only=True,
            keep_links=False,
        )
    except Exception as exc:
        raise QuoteFormParseError("Excel 无法解析，请确认文件未损坏或加密") from exc

    sheets = []
    try:
        for worksheet in workbook.worksheets[:MAX_SHEETS]:
            value_sheet = value_workbook[worksheet.title]
            source_rows = min(int(worksheet.max_row or 0), MAX_ROWS)
            source_cols = min(int(worksheet.max_column or 0), MAX_COLS)
            rows: list[list[str | int | float | bool | None]] = []
            if source_rows and source_cols:
                for row in worksheet.iter_rows(
                    min_row=1,
                    max_row=source_rows,
                    min_col=1,
                    max_col=source_cols,
                ):
                    rendered = []
                    for cell in row:
                        cached = value_sheet.cell(cell.row, cell.column).value
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
            sheets.append(
                {
                    "name": worksheet.title,
                    "rows": rows,
                    "row_count": len(rows),
                    "column_count": last_col,
                    "truncated": (
                        int(worksheet.max_row or 0) > MAX_ROWS
                        or int(worksheet.max_column or 0) > MAX_COLS
                    ),
                }
            )
    finally:
        workbook.close()
        if value_workbook is not None:
            value_workbook.close()

    if not sheets:
        raise QuoteFormParseError("Excel 没有可展示的工作表")
    return {
        "filename": Path(filename).name,
        "sheets": sheets,
        "sheet_count": len(sheets),
    }
