"""中国大陆手机号规范化。"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s\-()]+")
_MAINLAND_MOBILE = re.compile(r"^1[3-9]\d{9}$")


def canonicalize_mainland_mobile(raw: object) -> str:
    """返回 11 位大陆手机号；非法输入抛出 ``ValueError``。"""
    value = _SEPARATORS.sub("", str(raw or "").strip())
    if value.startswith("+86"):
        value = value[3:]
    elif value.startswith("0086"):
        value = value[4:]
    elif value.startswith("86") and len(value) == 13:
        value = value[2:]
    if not _MAINLAND_MOBILE.fullmatch(value):
        raise ValueError("手机号格式不正确")
    return value


def comparison_phone_key(raw: object) -> str:
    """历史数据比较键：合法号码取规范值，非法历史值只做分隔符清理。"""
    try:
        return canonicalize_mainland_mobile(raw)
    except ValueError:
        return _SEPARATORS.sub("", str(raw or "").strip())
