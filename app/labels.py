"""出参 label 解析（PLANNER-V3 §4.2 规则 3）。

页面显示名以 `dict_items` 为准 —— 用户在数据字典里把「成交」改成「已成交」，
所有出参 `*_label` 必须立刻跟着变；`enums.*_LABELS` 只是兜底（字典表还没建 / 该 key 没入库）。

性能：`dicts.label_map()` 自带 lru_cache，字典写操作后由 `invalidate()` 清空，所以这里
每次调用都只是查一次内存字典。
"""
from __future__ import annotations

from typing import Dict, Optional

from app import dicts as dict_svc
from app.enums import (
    AFTERSALE_STATUS_LABELS,
    AFTERSALE_TYPE_LABELS,
    CUSTOMER_TYPE_LABELS,
    DEAL_LOST_REASON_LABELS,
    DEAL_STAGE_LABELS,
    DRIVE_TYPE_LABELS,
    FOLLOW_METHOD_LABELS,
    INTENT_LEVEL_LABELS,
    LOGISTICS_MODE_LABELS,
    ORDER_STATUS_LABELS,
    SOURCE_LABELS,
    TIMELINE_TYPE_LABELS,
)


def _resolve(code: str, key: Optional[str], fallback: Dict[str, str]) -> Optional[str]:
    if not key:
        return None
    try:
        merged = {**fallback, **dict_svc.label_map(code)}
    except Exception:  # 字典表不可用时只走枚举兜底，别让出参 500
        merged = fallback
    return merged.get(key, key)


def invalidate() -> None:
    """字典写操作后调用（dicts router 已清一次，这里再清保险）。"""
    dict_svc.label_map.cache_clear()


def deal_stage(key: Optional[str]) -> Optional[str]:
    return _resolve("deal_stage", key, DEAL_STAGE_LABELS)


def order_status(key: Optional[str]) -> Optional[str]:
    return _resolve("order_status", key, ORDER_STATUS_LABELS)


def aftersale_status(key: Optional[str]) -> Optional[str]:
    return _resolve("aftersale_status", key, AFTERSALE_STATUS_LABELS)


def aftersale_type(key: Optional[str]) -> Optional[str]:
    return _resolve("aftersale_type", key, AFTERSALE_TYPE_LABELS)


def source(key: Optional[str]) -> Optional[str]:
    return _resolve("customer_source", key, SOURCE_LABELS)


def intent_level(key: Optional[str]) -> Optional[str]:
    return _resolve("intent_level", key, INTENT_LEVEL_LABELS)


def customer_type(key: Optional[str]) -> Optional[str]:
    return _resolve("customer_type", key, CUSTOMER_TYPE_LABELS)


def follow_method(key: Optional[str]) -> Optional[str]:
    return _resolve("follow_method", key, FOLLOW_METHOD_LABELS)


def lost_reason(key: Optional[str]) -> Optional[str]:
    return _resolve("lost_reason", key, DEAL_LOST_REASON_LABELS)


# —— 下面两个不是字典（系统定义），直接用枚举 ——
def drive_type(key: Optional[str]) -> Optional[str]:
    return DRIVE_TYPE_LABELS.get(key or "")


def logistics_mode(key: Optional[str]) -> Optional[str]:
    return LOGISTICS_MODE_LABELS.get(key or "")


def timeline_type(key: Optional[str]) -> Optional[str]:
    return TIMELINE_TYPE_LABELS.get(key or "", key)