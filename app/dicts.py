"""
CRM V2 数据字典注册表与 API 实现。
"""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

from app.db import db_conn
from app.enums import (
    AFTERSALE_STATUS,
    AFTERSALE_STATUS_LEGACY_LABELS,
    DEAL_STAGE,
    DRIVE_TYPE,
    FOLLOW_METHOD,
    LOGISTICS_MODE,
    TIMELINE_TYPE,
)


# ---------------- 字典注册表（唯一真源）----------------

DICT_REGISTRY = {
    # level: A=可增删改  B=仅改名+排序  C=仅改名  D=只读
    "product_model":    {"name": "产品型号",     "level": "A", "table": "deals.model"},
    "customer_source":  {"name": "客户来源",     "level": "A", "table": "leads.source,customers.source"},
    "intent_level":     {"name": "意向等级",     "level": "A", "table": "leads.intent_level,customers.intent_level"},
    "product_type":     {"name": "产品类型",     "level": "A", "table": "deals.product_type,orders.product_type"},
    "lost_reason":      {"name": "商机流失原因", "level": "A", "table": "deals.lost_reason"},
    "aftersale_type":   {"name": "售后类型",     "level": "A", "table": "aftersales.type"},
    "follow_method":    {"name": "跟进方式",     "level": "A", "table": "follow_ups.method"},
    "deal_stage":       {"name": "商机阶段",     "level": "B", "table": "deals.stage"},
    "order_status":     {"name": "订单状态",     "level": "B", "table": "orders.status"},
    "aftersale_status": {"name": "售后状态",     "level": "B", "table": "aftersales.status"},
    "customer_type":    {"name": "客户类型",     "level": "C", "table": "customers.customer_type,leads.lead_type"},
    "follow_object":    {"name": "跟进对象类型", "level": "D", "table": "follow_ups.object_type"},
}


# ---------------- 字典描述（给前端总览页用）----------------

DICT_DESC = {
    "product_model":    "商机/订单的型号下拉，选中自动带出尺寸",
    "customer_source":  "客户建档 / 线索来源",
    "intent_level":     "客户 / 线索的购买意向",
    "product_type":     "商机 / 订单的产品分类",
    "lost_reason":      "商机判流失时必选",
    "aftersale_type":   "售后单类型",
    "follow_method":    "记跟进时的方式（微信 / 电话）",
    "deal_stage":       "状态机：报价 → 待客户确认 → 成交 / 流失，只能改名",
    "order_status":     "状态机：8 态，只能改名/排序",
    "aftersale_status": "状态机：待处理 → 处理中 → 已完成",
    "customer_type":    "个人 / 公司 / 其他，绑定「公司名是否必填」，只能改名",
    "follow_object":    "系统定义的跟进对象类型，只读",
}


# ---------------- 字典种子数据（用于降级）----------------

DICT_SEEDS = {
    "product_model": [
        {"key": "XW-60", "label": "XW-60 天窗 600×1200", "sort": 1, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "600×1200", "drive": "manual"}},
        {"key": "XW-90", "label": "XW-90 天窗 900×1800", "sort": 2, "enabled": True, "used": 3, "meta": {"product": "天窗", "size": "900×1800", "drive": "manual"}},
        {"key": "XW-120", "label": "XW-120 天窗 1200×2400", "sort": 3, "enabled": True, "used": 5, "meta": {"product": "天窗", "size": "1200×2400", "drive": "manual"}},
        {"key": "XW-150", "label": "XW-150 天窗 1500×2800", "sort": 4, "enabled": True, "used": 1, "meta": {"product": "天窗", "size": "1500×2800", "drive": "manual"}},
        {"key": "XW-180", "label": "XW-180 天窗 1800×3000", "sort": 5, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "1800×3000", "drive": "manual"}},
        {"key": "XW-120E", "label": "XW-120E 天窗 电动款 1200×2400", "sort": 6, "enabled": True, "used": 2, "meta": {"product": "天窗", "size": "1200×2400", "drive": "electric"}},
        {"key": "XW-150E", "label": "XW-150E 天窗 电动款 1500×2800", "sort": 7, "enabled": True, "used": 1, "meta": {"product": "天窗", "size": "1500×2800", "drive": "electric"}},
        {"key": "XW-200E", "label": "XW-200E 天窗 电动款 2000×3200", "sort": 8, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "2000×3200", "drive": "electric"}},
        {"key": "TM-120", "label": "TM-120 天幕 1200×2000", "sort": 9, "enabled": True, "used": 0, "meta": {"product": "天幕", "size": "1200×2000", "drive": "manual"}},
        {"key": "TM-180", "label": "TM-180 天幕 1800×2600", "sort": 10, "enabled": True, "used": 1, "meta": {"product": "天幕", "size": "1800×2600", "drive": "manual"}},
        {"key": "TM-240", "label": "TM-240 天幕 2400×3000", "sort": 11, "enabled": True, "used": 2, "meta": {"product": "天幕", "size": "2400×3000", "drive": "manual"}},
        {"key": "TM-300", "label": "TM-300 天幕 3000×3500", "sort": 12, "enabled": True, "used": 1, "meta": {"product": "天幕", "size": "3000×3500", "drive": "manual"}},
        {"key": "TM-360", "label": "TM-360 天幕 3600×4200", "sort": 13, "enabled": True, "used": 0, "meta": {"product": "天幕", "size": "3600×4200", "drive": "manual"}},
        {"key": "TM-240E", "label": "TM-240E 天幕 电动款 2400×3000", "sort": 14, "enabled": True, "used": 1, "meta": {"product": "天幕", "size": "2400×3000", "drive": "electric"}},
        {"key": "TM-300E", "label": "TM-300E 天幕 电动款 3000×3500", "sort": 15, "enabled": True, "used": 0, "meta": {"product": "天幕", "size": "3000×3500", "drive": "electric"}},
        {"key": "YG-20", "label": "YG-20 阳光房 2000×3000", "sort": 16, "enabled": True, "used": 0, "meta": {"product": "阳光房", "size": "2000×3000", "drive": "manual"}},
        {"key": "YG-30", "label": "YG-30 阳光房 3000×4000", "sort": 17, "enabled": True, "used": 2, "meta": {"product": "阳光房", "size": "3000×4000", "drive": "manual"}},
        {"key": "YG-40", "label": "YG-40 阳光房 4000×5000", "sort": 18, "enabled": True, "used": 0, "meta": {"product": "阳光房", "size": "4000×5000", "drive": "manual"}},
        {"key": "YG-50", "label": "YG-50 阳光房 5000×6000", "sort": 19, "enabled": True, "used": 0, "meta": {"product": "阳光房", "size": "5000×6000", "drive": "manual"}},
        {"key": "ZY-10", "label": "ZY-10 遮阳帘 1000×1500", "sort": 20, "enabled": True, "used": 0, "meta": {"product": "遮阳帘", "size": "1000×1500", "drive": "manual"}},
        {"key": "ZY-15", "label": "ZY-15 遮阳帘 1500×2000", "sort": 21, "enabled": True, "used": 1, "meta": {"product": "遮阳帘", "size": "1500×2000", "drive": "manual"}},
        {"key": "ZY-20", "label": "ZY-20 遮阳帘 2000×2500", "sort": 22, "enabled": True, "used": 0, "meta": {"product": "遮阳帘", "size": "2000×2500", "drive": "manual"}},
        {"key": "ZY-25E", "label": "ZY-25E 遮阳帘 电动款 2500×3000", "sort": 23, "enabled": True, "used": 0, "meta": {"product": "遮阳帘", "size": "2500×3000", "drive": "electric"}},
        {"key": "FT-100", "label": "FT-100 上翻窗 1000×1000", "sort": 24, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "1000×1000", "drive": "manual"}},
        {"key": "FT-140", "label": "FT-140 上翻窗 1400×1400", "sort": 25, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "1400×1400", "drive": "manual"}},
        {"key": "PY-120", "label": "PY-120 平移窗 1200×1200", "sort": 26, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "1200×1200", "drive": "manual"}},
        {"key": "PY-160", "label": "PY-160 平移窗 1600×1200", "sort": 27, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "1600×1200", "drive": "manual"}},
        {"key": "PY-200E", "label": "PY-200E 平移窗 电动款 2000×1500", "sort": 28, "enabled": True, "used": 0, "meta": {"product": "天窗", "size": "2000×1500", "drive": "electric"}},
        {"key": "YG-30E", "label": "YG-30E 阳光房 电动开合 3000×4000", "sort": 29, "enabled": True, "used": 0, "meta": {"product": "阳光房", "size": "3000×4000", "drive": "electric"}},
        {"key": "TM-420", "label": "TM-420 天幕 4200×5000", "sort": 30, "enabled": True, "used": 0, "meta": {"product": "天幕", "size": "4200×5000", "drive": "manual"}},
    ],
    "customer_source": [
        {"key": "wechat", "label": "微信", "sort": 1, "enabled": True, "used": 0},
        {"key": "phone", "label": "电话", "sort": 2, "enabled": True, "used": 0},
        {"key": "referral", "label": "转介绍", "sort": 3, "enabled": True, "used": 0},
        {"key": "existing", "label": "老客户", "sort": 4, "enabled": True, "used": 0},
        {"key": "stock", "label": "存量", "sort": 5, "enabled": True, "used": 0},
        {"key": "other", "label": "其他", "sort": 6, "enabled": True, "used": 0},
        {"key": "video_account", "label": "视频号", "sort": 1001, "enabled": True, "used": 0},
        {"key": "xianyu", "label": "咸鱼", "sort": 1002, "enabled": True, "used": 0},
    ],
    "intent_level": [
        {"key": "high", "label": "高", "sort": 1, "enabled": True, "used": 0},
        {"key": "medium", "label": "中", "sort": 2, "enabled": True, "used": 0},
        {"key": "low", "label": "低", "sort": 3, "enabled": True, "used": 0},
        {"key": "none", "label": "无意向", "sort": 4, "enabled": True, "used": 0},
    ],
    "product_type": [
        {"key": "天窗", "label": "天窗", "sort": 1, "enabled": True, "used": 0},
        {"key": "天幕", "label": "天幕", "sort": 2, "enabled": True, "used": 0},
        {"key": "阳光房", "label": "阳光房", "sort": 3, "enabled": True, "used": 0},
        {"key": "遮阳帘", "label": "遮阳帘", "sort": 4, "enabled": True, "used": 0},
    ],
    "lost_reason": [
        {"key": "price", "label": "价格", "sort": 1, "enabled": True, "used": 0},
        {"key": "competitor", "label": "竞品", "sort": 2, "enabled": True, "used": 0},
        {"key": "give_up", "label": "客户放弃", "sort": 3, "enabled": True, "used": 0},
        {"key": "budget", "label": "预算不足", "sort": 4, "enabled": True, "used": 0},
        {"key": "other", "label": "其他", "sort": 5, "enabled": True, "used": 0},
    ],
    "aftersale_type": [
        {"key": "return", "label": "退货", "sort": 1, "enabled": True, "used": 0},
        {"key": "exchange", "label": "换货", "sort": 2, "enabled": True, "used": 0},
        {"key": "repair", "label": "维修", "sort": 3, "enabled": True, "used": 0},
        {"key": "complaint", "label": "投诉", "sort": 4, "enabled": True, "used": 0},
        {"key": "other", "label": "其他", "sort": 5, "enabled": True, "used": 0},
    ],
    "follow_method": [
        {"key": "wechat", "label": "微信", "sort": 1, "enabled": True, "used": 0},
        {"key": "phone", "label": "电话", "sort": 2, "enabled": True, "used": 0},
    ],
    "deal_stage": [
        {"key": "quote", "label": "报价", "sort": 1, "enabled": True, "used": 0},
        {"key": "confirm", "label": "待客户确认", "sort": 2, "enabled": True, "used": 0},
        {"key": "won", "label": "成交", "sort": 3, "enabled": True, "used": 0},
        {"key": "lost", "label": "流失", "sort": 4, "enabled": True, "used": 0},
    ],
    "order_status": [
        {"key": "pending_confirmation", "label": "待客户确认", "sort": 1, "enabled": True, "used": 0},
        {"key": "pending_payment", "label": "待支付", "sort": 2, "enabled": True, "used": 0},
        {"key": "deposit_paid", "label": "已支付定金", "sort": 3, "enabled": True, "used": 0},
        {"key": "producing", "label": "生产中", "sort": 4, "enabled": True, "used": 0},
        {"key": "balance_paid", "label": "已支付尾款", "sort": 5, "enabled": True, "used": 0},
        {"key": "ready_to_ship", "label": "待发货", "sort": 6, "enabled": True, "used": 0},
        {"key": "shipped", "label": "已发货", "sort": 7, "enabled": True, "used": 0},
        {"key": "completed", "label": "已完成", "sort": 8, "enabled": True, "used": 0},
    ],
    "aftersale_status": [
        {"key": "pending", "label": "待处理", "sort": 1, "enabled": True, "used": 0},
        {"key": "processing", "label": "处理中", "sort": 2, "enabled": True, "used": 0},
        {"key": "done", "label": "已完成", "sort": 3, "enabled": True, "used": 0},
    ],
    # 2026-10-31 用户定稿：公司排第 1，个人排第 2
    "customer_type": [
        {"key": "company", "label": "公司", "sort": 1, "enabled": True, "used": 0},
        {"key": "personal", "label": "个人", "sort": 2, "enabled": True, "used": 0},
        {"key": "other", "label": "其他", "sort": 3, "enabled": True, "used": 0},
    ],
    "follow_object": [
        {"key": "lead", "label": "线索", "sort": 1, "enabled": True, "used": 0},
        {"key": "customer", "label": "客户", "sort": 2, "enabled": True, "used": 0},
        {"key": "deal", "label": "商机", "sort": 3, "enabled": True, "used": 0},
        {"key": "order", "label": "订单", "sort": 4, "enabled": True, "used": 0},
        {"key": "aftersale", "label": "售后", "sort": 5, "enabled": True, "used": 0},
    ],
}

# ---------------- 查询（DB 优先；表缺失时降级到种子）----------------


class _NoDictTable(Exception):
    """dict_items 表还不存在（迁移跑到一半）—— 用种子兜底。"""


def _loads(raw: Any) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else None
    except (TypeError, ValueError):
        return None


def _table_ready(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dict_items'"
        ).fetchone()
        is not None
    )


@lru_cache(maxsize=256)
def label_map(code: str) -> Dict[str, str]:
    """key -> 显示名（含停用项；历史数据仍要显示中文）。写操作后必须 cache_clear()。"""
    return {item["key"]: item["label"] for item in items(code, include_disabled=True)}


def _usage_by_key(conn: sqlite3.Connection, code: str) -> Dict[str, int]:
    """单次分组查询算「被引用次数」，不逐项 COUNT。"""
    entry = DICT_REGISTRY.get(code) or {}
    usage: Dict[str, int] = {}
    for pair in str(entry.get("table") or "").split(","):
        pair = pair.strip()
        if "." not in pair:
            continue
        table, column = pair.split(".", 1)
        try:
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
            where = " WHERE is_delete = 0" if "is_delete" in columns else ""
            rows = conn.execute(
                f"SELECT {column} AS k, COUNT(*) AS n FROM {table}{where}"
                f" GROUP BY {column}"
            ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            key = row["k"]
            if key is None or str(key) == "":
                continue
            usage[str(key)] = usage.get(str(key), 0) + int(row["n"])
    return usage


def items(code: str, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """字典项列表 `[{key,label,sort,enabled,used,meta}]`（按 sort 升序）。

    - 表存在：读 `dict_items`，`used` 实时统计业务表；
    - 表不存在：降级到 `DICT_SEEDS`，`used=0`（不抛错，服务照常启动）。
    """
    if code not in DICT_REGISTRY:
        return []
    try:
        with db_conn() as conn:
            if not _table_ready(conn):
                raise _NoDictTable()
            sql = (
                "SELECT key, label, sort, enabled, meta FROM dict_items"
                " WHERE dict_code = ? AND is_delete = 0"
            )
            params: List[Any] = [code]
            if not include_disabled:
                sql += " AND enabled = 1"
            sql += " ORDER BY sort, id"
            rows = conn.execute(sql, params).fetchall()
            usage = _usage_by_key(conn, code)
            return [
                {
                    "key": row["key"],
                    "label": row["label"],
                    "sort": int(row["sort"] or 0),
                    "enabled": bool(row["enabled"]),
                    "used": usage.get(str(row["key"]), 0),
                    "meta": _loads(row["meta"]),
                }
                for row in rows
            ]
    except _NoDictTable:
        return [
            {
                "key": seed["key"],
                "label": seed["label"],
                "sort": int(seed.get("sort") or 0),
                "enabled": bool(seed.get("enabled", True)),
                "used": 0,
                "meta": _loads(seed.get("meta")),
            }
            for seed in DICT_SEEDS.get(code, [])
            if include_disabled or seed.get("enabled", True)
        ]


def exists(code: str, key: str) -> bool:
    """字典项是否存在（含停用项）——改/删用这个。"""
    try:
        with db_conn() as conn:
            if not _table_ready(conn):
                raise _NoDictTable()
            return (
                conn.execute(
                    "SELECT 1 FROM dict_items"
                    " WHERE dict_code = ? AND key = ? AND is_delete = 0",
                    (code, key),
                ).fetchone()
                is not None
            )
    except _NoDictTable:
        return any(seed["key"] == key for seed in DICT_SEEDS.get(code, []))


def validate(code: str, key: str) -> bool:
    """新建/编辑业务数据时用：必须存在且启用。"""
    try:
        with db_conn() as conn:
            if not _table_ready(conn):
                raise _NoDictTable()
            return (
                conn.execute(
                    "SELECT 1 FROM dict_items"
                    " WHERE dict_code = ? AND key = ? AND enabled = 1 AND is_delete = 0",
                    (code, key),
                ).fetchone()
                is not None
            )
    except _NoDictTable:
        return any(
            seed["key"] == key and seed.get("enabled", True) for seed in DICT_SEEDS.get(code, [])
        )


def used_count(code: str, key: str) -> int:
    """某个字典项被业务数据引用多少次（跨注册表里的所有表/列）。"""
    try:
        with db_conn() as conn:
            return _usage_by_key(conn, code).get(str(key), 0)
    except sqlite3.Error:
        return 0


def level(code: str) -> str:
    return DICT_REGISTRY.get(code, {}).get("level", "D")


def desc(code: str) -> str:
    return DICT_DESC.get(code, "")


def codes() -> List[str]:
    return list(DICT_REGISTRY.keys())


# ---------------- 写操作（分级权限由 router 判，这里只保证数据正确）----------------


def create_item(code: str, key: str, label: str, sort: int = 0,
                enabled: bool = True, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO dict_items"
            " (dict_code, key, label, sort, enabled, meta, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))"
            " ON CONFLICT(dict_code, key) DO UPDATE SET"
            " label = excluded.label, sort = excluded.sort, enabled = excluded.enabled,"
            " meta = excluded.meta, is_delete = 0, updated_at = datetime('now'),"
            " update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
            (
                code,
                key,
                label,
                int(sort),
                1 if enabled else 0,
                json.dumps(meta, ensure_ascii=False) if meta else None,
            ),
        )
    label_map.cache_clear()
    return get_item(code, key)


def update_item(code: str, key: str, **fields: Any) -> Dict[str, Any]:
    allowed = {"label", "sort", "enabled", "meta"}
    sets, values = [], []
    for name, value in fields.items():
        if name not in allowed or value is None:
            continue
        if name == "enabled":
            value = 1 if value else 0
        elif name == "meta":
            value = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        sets.append(f"{name} = ?")
        values.append(value)
    if not sets:
        raise ValueError("没有可更新的字段")
    with db_conn() as conn:
        conn.execute(
            f"UPDATE dict_items SET {', '.join(sets)}, updated_at = datetime('now')"
            " WHERE dict_code = ? AND key = ? AND is_delete = 0",
            [*values, code, key],
        )
    label_map.cache_clear()
    return get_item(code, key)


def reorder_items(code: str, keys: List[str]) -> List[Dict[str, Any]]:
    """按传入的 key 顺序重排当前启用项；整批更新在同一事务内完成。"""
    current_keys = [item["key"] for item in items(code)]
    if len(keys) != len(current_keys) or set(keys) != set(current_keys):
        raise ValueError("排序列表必须包含当前全部启用选项，且不能重复")

    with db_conn() as conn:
        for sort, key in enumerate(keys, start=1):
            conn.execute(
                "UPDATE dict_items SET sort = ?, updated_at = datetime('now')"
                " WHERE dict_code = ? AND key = ? AND enabled = 1 AND is_delete = 0",
                (sort, code, key),
            )
    label_map.cache_clear()
    return items(code)


def delete_item(code: str, key: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "UPDATE dict_items SET is_delete = 1,"
            " update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            " WHERE dict_code = ? AND key = ?",
            (code, key),
        )
    label_map.cache_clear()


def get_item(code: str, key: str) -> Dict[str, Any]:
    for item in items(code, include_disabled=True):
        if item["key"] == key:
            return item
    raise KeyError(f"{code}/{key} 不存在")


def search_product_models(q: Optional[str] = None, product: Optional[str] = None) -> List[Dict[str, Any]]:
    """型号可搜索下拉：匹配 key / label / meta.size（大小写不敏感）。"""
    keyword = (q or "").strip().lower()
    result = []
    for item in items("product_model"):
        meta = item.get("meta") or {}
        if product and meta.get("product") != product:
            continue
        if keyword:
            haystack = " ".join([
                str(item["key"]),
                str(item["label"]),
                str(meta.get("size") or ""),
            ]).lower()
            if keyword not in haystack:
                continue
        result.append(item)
    return result
