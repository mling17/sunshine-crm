"""Infer product-master fields from an uploaded Excel order form.

Only workbook titles and selected product-description terms are used. Customer
names, addresses, prices and one-off dimensions are deliberately ignored.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any


MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_SHEETS_TO_SCAN = 6
MAX_SCAN_ROWS = 24
MAX_SCAN_COLS = 24

CN_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}

LABEL_WORDS = (
    "日期", "产品名称", "加工尺寸", "收货人", "收货地址", "联系电话",
    "金额", "备注", "合计", "销售员", "制单员", "序号", "数量",
)


class ProductFormParseError(ValueError):
    """Raised when an uploaded workbook cannot be read as an order form."""


def _compact(value: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_file_stem(filename: str) -> str:
    stem = Path(filename or "下单表.xlsx").stem.strip()
    stem = re.sub(r"^[（(]\s*新\s*[）)]\s*", "", stem)
    return re.sub(r"\s+", " ", stem).strip() or "新下单表产品"


def _validate_zip_container(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ProductFormParseError("文件内容不是有效的 Excel 工作簿")
            uncompressed = sum(item.file_size for item in archive.infolist())
            if uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise ProductFormParseError("Excel 解压后内容过大，无法安全识别")
    except zipfile.BadZipFile as exc:
        raise ProductFormParseError("文件内容不是有效的 Excel 工作簿") from exc


def _scan_workbook(data: bytes) -> tuple[str, list[str], list[str]]:
    _validate_zip_container(data)
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ProductFormParseError("服务端缺少 Excel 解析组件，请联系管理员") from exc

    try:
        workbook = load_workbook(
            io.BytesIO(data),
            read_only=True,
            data_only=True,
            keep_links=False,
        )
    except Exception as exc:
        raise ProductFormParseError("Excel 文件无法解析，请确认文件未损坏或加密") from exc

    try:
        sheet_names = list(workbook.sheetnames[:MAX_SHEETS_TO_SCAN])
        title_candidates: list[tuple[int, str]] = []
        text_values: list[str] = []
        for sheet_index, worksheet in enumerate(workbook.worksheets[:MAX_SHEETS_TO_SCAN]):
            max_row = min(int(worksheet.max_row or 0), MAX_SCAN_ROWS)
            max_col = min(int(worksheet.max_column or 0), MAX_SCAN_COLS)
            if max_row <= 0 or max_col <= 0:
                continue
            for row in worksheet.iter_rows(
                min_row=1,
                max_row=max_row,
                max_col=max_col,
            ):
                for cell in row:
                    if not isinstance(cell.value, str):
                        continue
                    value = _compact(cell.value)
                    if not value or len(value) > 180:
                        continue
                    text_values.append(value)
                    if len(value) < 4 or len(value) > 90:
                        continue
                    if any(word in value for word in LABEL_WORDS):
                        continue
                    if value.lower() in {"sheet1", "sheet2", "sheet3"}:
                        continue
                    score = len(value)
                    if "下单表" in value:
                        score += 120
                    if any(
                        word in value
                        for word in (
                            "天窗", "天幕", "型", "平放", "嵌入", "平起",
                            "平移", "联排", "对开", "纱窗", "遮阳", "屋面",
                        )
                    ):
                        score += 60
                    if cell.row <= 8:
                        score += 30
                    if sheet_index == 0:
                        score += 10
                    title_candidates.append((score, value))
    finally:
        workbook.close()

    title = ""
    if title_candidates:
        title = max(title_candidates, key=lambda item: item[0])[1]
    return title, text_values, sheet_names


def _series_for(text: str) -> tuple[str, bool]:
    rules = (
        (r"(?<!\d)(?:300|340)(?!\d)", "300/340型"),
        (r"(?<!\d)540(?!\d)", "540型"),
        (r"(?<!\d)480(?!\d)", "480型"),
        (r"(?<!\d)140(?!\d)", "140型"),
        (r"(?<!\d)95(?=型|新扇|老扇|高低扇|平起|断桥|联排|对开)", "95型"),
        (r"(?<!\d)55(?=型|平起|联排|对开|新扇|老扇|高低扇|断桥)", "55型"),
        (r"(?:25断桥|(?<!\d)25(?=型|新扇|老扇|高低扇|平起|断桥|联排|对开))", "25型"),
    )
    for pattern, value in rules:
        if re.search(pattern, text):
            return value, True
    if "工程天窗" in text:
        return "工程型", True
    return "通用", False


def _structure_for(text: str) -> tuple[str, bool]:
    rules = (
        ("隐藏排水", "隐藏排水"),
        ("排水板", "排水板"),
        ("隐藏螺杆", "隐藏螺杆"),
        ("折叠平移", "折叠平移"),
        ("框扇一体", "框扇一体平移"),
        ("L平移", "L型平移"),
        ("三角形", "三角形"),
        ("开合屋面", "开合屋面"),
        ("平移", "平移"),
        ("平起", "平起"),
        ("嵌入", "嵌入"),
        ("内嵌", "嵌入"),
        ("下陷", "嵌入"),
        ("平放", "平放"),
        ("天幕", "天幕"),
    )
    for needle, value in rules:
        if needle in text:
            return value, True
    return "标准", False


def _opening_for(text: str) -> tuple[str, bool]:
    if "高低扇" in text:
        return "高低扇", True
    if "对开" in text:
        return "对开", True
    if "联排" in text or re.search(r"[二两三四五六]连排", text):
        return "联排", True
    if "折叠" in text:
        return "折叠滑动", True
    if "开合屋面" in text:
        return "固定+活动", True
    if "固定" in text and any(word in text for word in ("开启", "活动", "开扇")):
        return "固定+开启", True
    if "平移" in text:
        return "平移", True
    if "单扇" in text:
        return "单扇开启", True
    return "单扇开启", False


def _drive_for(text: str) -> str | None:
    if "电动" in text:
        return "electric"
    if "手动" in text or "普通开启" in text:
        return "manual"
    return None


def _frame_for(text: str) -> tuple[str, bool]:
    rules = (
        ("极窄", "极窄"),
        ("断桥", "断桥"),
        ("隐藏型材", "隐藏型材"),
        ("重型", "重型"),
        ("大料", "大料"),
        ("普通", "普通"),
    )
    for needle, value in rules:
        if needle in text:
            return value, True
    return "标准", False


def _leaf_for(text: str) -> tuple[str, bool]:
    for value in ("高低扇", "新扇", "老扇", "大料"):
        if value in text:
            return value, True
    return "标准", False


def _edge_for(text: str) -> str | None:
    if "不带边" in text:
        return "不带边"
    if "带边" in text:
        return "带边"
    return None


def _leaf_count_for(text: str) -> int | None:
    if "单扇" in text:
        return 1
    fixed = re.search(r"([一二两三四五六])固定", text)
    active = re.search(r"([一二两三四五六])(?:开扇|开启|活动)", text)
    if fixed and active:
        return CN_NUMBERS[fixed.group(1)] + CN_NUMBERS[active.group(1)]
    direct = re.search(r"([1-9])扇", text)
    if direct:
        return int(direct.group(1))
    chinese = re.search(r"([二两三四五六])(?:扇)?(?:联排|连排)", text)
    if chinese:
        return CN_NUMBERS[chinese.group(1)]
    return None


def _category_for(text: str, structure: str, series: str) -> str:
    if structure == "开合屋面":
        return "开合屋面"
    if structure == "天幕" or "天幕" in text:
        return "天幕"
    if "遮阳" in text and series == "通用" and "天窗" not in text:
        return "遮阳"
    if "纱窗" in text and series == "通用" and "天窗" not in text:
        return "纱窗"
    return "天窗"


def _attributes_for(text: str) -> dict[str, str | None]:
    if "电动纱窗" in text or "电动纱网" in text:
        screen = "电动纱窗"
    elif "手动纱窗" in text:
        screen = "手动纱窗"
    elif "纱窗" in text or "纱网" in text:
        screen = "纱窗"
    else:
        screen = None

    if "电动遮阳" in text:
        shade = "电动遮阳"
    elif "手动遮阳" in text or "遮阳" in text:
        shade = "手动遮阳"
    else:
        shade = None

    if "内置无钥匙隔热把手" in text:
        handle = "内置无钥匙隔热把手"
    elif "内置不带钥匙" in text:
        handle = "内置无钥匙隔热把手"
    elif "外置带钥匙" in text or "带钥匙隔热把手" in text:
        handle = "外置带钥匙隔热把手"
    elif "隔热把手" in text:
        handle = "隔热把手"
    elif "普通把手" in text:
        handle = "普通把手"
    else:
        handle = None

    motor_cover = None
    if "电机罩" in text:
        motor_cover = "L型" if "L电机罩" in text else "标准"

    return {
        "screen": screen,
        "mesh": "金刚网" if "金刚网" in text else None,
        "motor_cover": motor_cover,
        "shade": shade,
        "handle": handle,
    }


def parse_order_form(data: bytes, filename: str) -> dict[str, Any]:
    """Return product-master fields inferred from one order-form workbook."""
    if Path(filename).suffix.lower() != ".xlsx":
        raise ProductFormParseError("自动识别仅支持 .xlsx；旧版 .xls 请另存为 .xlsx")

    title, text_values, sheet_names = _scan_workbook(data)
    stem = _safe_file_stem(filename)
    identity = " ".join(filter(None, [stem, title, *sheet_names]))
    feature_terms = (
        "电动纱窗", "手动纱窗", "纱窗", "金刚网", "电机罩", "L电机罩",
        "电动遮阳", "手动遮阳", "遮阳", "隔热把手", "普通把手",
        "内置无钥匙", "内置不带钥匙", "外置带钥匙",
    )
    feature_text = identity
    for value in text_values[:800]:
        if any(term in value for term in feature_terms):
            feature_text += " " + value

    series, series_found = _series_for(identity)
    structure, structure_found = _structure_for(identity)
    opening_mode, opening_found = _opening_for(identity)
    frame_type, frame_found = _frame_for(identity)
    leaf_type, leaf_found = _leaf_for(identity)
    name = _compact(title or stem, 120)

    warnings: list[str] = []
    if not title:
        warnings.append("未识别到下单表标题，产品名称暂用文件名")
    if not series_found:
        warnings.append("未识别产品系列，已设为「通用」")
    if not structure_found:
        warnings.append("未识别结构方式，已设为「标准」")
    if not opening_found:
        warnings.append("未识别开启方式，已暂设「单扇开启」")
    if not frame_found:
        warnings.append("未识别型材 / 边框，已设为「标准」")
    if not leaf_found:
        warnings.append("未识别扇型，已设为「标准」")

    result: dict[str, Any] = {
        "name": name,
        "category": _category_for(identity, structure, series),
        "series": series,
        "structure": structure,
        "opening_mode": opening_mode,
        "drive_type": _drive_for(identity),
        "frame_type": frame_type,
        "leaf_type": leaf_type,
        "edge_type": _edge_for(identity),
        "leaf_count": _leaf_count_for(identity),
        "attributes": _attributes_for(feature_text),
        "source_template": filename,
        "description": f"由下单表「{filename}」自动识别，请核对配置信息。",
        "is_active": True,
        "warnings": warnings,
    }
    if result["drive_type"] is None:
        warnings.append("未识别手动 / 电动驱动方式，请核对")
    return result
