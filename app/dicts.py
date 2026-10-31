"""
CRM V2 数据字典注册表与 API 实现。
"""
from __future__ import annotations

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


# ---------------- 字典种子数据（用于降级）----------------

DICT_SEEDS = {
    "product_model": [
        {"key": "XW-60", "label": "XW-60 天窗 600×1200", "sort": 1, "enabled": True, "used": 0},
        {"key": "XW-90", "label": "XW-90 天窗 900×1800", "sort": 2, "enabled": True, "used": 3},
        {"key": "XW-120", "label": "XW-120 天窗 1200×2400", "sort": 3, "enabled": True, "used": 5},
        {"key": "XW-150", "label": "XW-150 天窗 1500×2800", "sort": 4, "enabled": True, "used": 1},
        {"key": "XW-180", "label": "XW-180 天窗 1800×3000", "sort": 5, "enabled": True, "used": 0},
        {"key": "XW-120E", "label": "XW-120E 天窗 电动款 1200×2400", "sort": 6, "enabled": True, "used": 2},
        {"key": "XW-150E", "label": "XW-150E 天窗 电动款 1500×2800", "sort": 7, "enabled": True, "used": 1},
        {"key": "XW-200E", "label": "XW-200E 天窗 电动款 2000×3200", "sort": 8, "enabled": True, "used": 0},
        {"key": "TM-120", "label": "TM-120 天幕 1200×2000", "sort": 9, "enabled": True, "used": 0},
        {"key": "TM-180", "label": "TM-180 天幕 1800×2600", "sort": 10, "enabled": True, "used": 1},
        {"key": "TM-240", "label": "TM-240 天幕 2400×3000", "sort": 11, "enabled": True, "used": 2},
        {"key": "TM-300", "label": "TM-300 天幕 3000×3500", "sort": 12, "enabled": True, "used": 1},
        {"key": "TM-360", "label": "TM-360 天幕 3600×4200", "sort": 13, "enabled": True, "used": 0},
        {"key": "TM-240E", "label": "TM-240E 天幕 电动款 2400×3000", "sort": 14, "enabled": True, "used": 1},
        {"key": "TM-300E", "label": "TM-300E 天幕 电动款 3000×3500", "sort": 15, "enabled": True, "used": 0},
        {"key": "YG-20", "label": "YG-20 阳光房 2000×3000", "sort": 16, "enabled": True, "used": 0},
        {"key": "YG-30", "label": "YG-30 阳光房 3000×4000", "sort": 17, "enabled": True, "used": 2},
        {"key": "YG-40", "label": "YG-40 阳光房 4000×5000", "sort": 18, "enabled": True, "used": 0},
        {"key": "YG-50", "label": "YG-50 阳光房 5000×6000", "sort": 19, "enabled": True, "used": 0},
        {"key": "ZY-10", "label": "ZY-10 遮阳帘 1000×1500", "sort": 20, "enabled": True, "used": 0},
        {"key": "ZY-15", "label": "ZY-15 遮阳帘 1500×2000", "sort": 21, "enabled": True, "used": 1},
        {"key": "ZY-20", "label": "ZY-20 遮阳帘 2000×2500", "sort": 22, "enabled": True, "used": 0},
        {"key": "ZY-25E", "label": "ZY-25E 遮阳帘 电动款 2500×3000", "sort": 23, "enabled": True, "used": 0},
        {"key": "FT-100", "label": "FT-100 上翻窗 1000×1000", "sort": 24, "enabled": True, "used": 0},
        {"key": "FT-140", "label": "FT-140 上翻窗 1400×1400", "sort": 25, "enabled": True, "used": 0},
        {"key": "PY-120", "label": "PY-120 平移窗 1200×1200", "sort": 26, "enabled": True, "used": 0},
        {"key": "PY-160", "label": "PY-160 平移窗 1600×1200", "sort": 27, "enabled": True, "used": 0},
        {"key": "PY-200E", "label": "PY-200E 平移窗 电动款 2000×1500", "sort": 28, "enabled": True, "used": 0},
        {"key": "YG-30E", "label": "YG-30E 阳光房 电动开合 3000×4000", "sort": 29, "enabled": True, "used": 0},
        {"key": "TM-420", "label": "TM-420 天幕 4200×5000", "sort": 30, "enabled": True, "used": 0},
    ],
    "customer_source": [
        {"key": "wechat", "label": "微信", "sort": 1, "enabled": True, "used": 0},
        {"key": "phone", "label": "电话", "sort": 2, "enabled": True, "used": 0},
        {"key": "referral", "label": "转介绍", "sort": 3, "enabled": True, "used": 0},
        {"key": "existing", "label": "老客户", "sort": 4, "enabled": True, "used": 0},
        {"key": "stock", "label": "存量", "sort": 5, "enabled": True, "used": 0},
        {"key": "other", "label": "其他", "sort": 6, "enabled": True, "used": 0},
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
        {"key": "pending_payment", "label": "待支付", "sort": 1, "enabled": True, "used": 0},
        {"key": "deposit_paid", "label": "已支付押金", "sort": 2, "enabled": True, "used": 0},
        {"key": "producing", "label": "生产中", "sort": 3, "enabled": True, "used": 0},
        {"key": "balance_paid", "label": "已支付尾款", "sort": 4, "enabled": True, "used": 0},
        {"key": "ready_to_ship", "label": "待发货", "sort": 5, "enabled": True, "used": 0},
        {"key": "shipped", "label": "已发货", "sort": 6, "enabled": True, "used": 0},
        {"key": "completed", "label": "已完成", "sort": 7, "enabled": True, "used": 0},
    ],
    "aftersale_status": [
        {"key": "pending", "label": "待处理", "sort": 1, "enabled": True, "used": 0},
        {"key": "processing", "label": "处理中", "sort": 2, "enabled": True, "used": 0},
        {"key": "done", "label": "已完成", "sort": 3, "enabled": True, "used": 0},
    ],
    "customer_type": [
        {"key": "personal", "label": "个人", "sort": 1, "enabled": True, "used": 0},
        {"key": "company", "label": "公司", "sort": 2, "enabled": True, "used": 0},
    ],
    "follow_object": [
        {"key": "lead", "label": "线索", "sort": 1, "enabled": True, "used": 0},
        {"key": "customer", "label": "客户", "sort": 2, "enabled": True, "used": 0},
        {"key": "deal", "label": "商机", "sort": 3, "enabled": True, "used": 0},
        {"key": "order", "label": "订单", "sort": 4, "enabled": True, "used": 0},
        {"key": "aftersale", "label": "售后", "sort": 5, "enabled": True, "used": 0},
    ],
}


# ---------------- 字典查询函数 ----------------

@lru_cache(maxsize=128)
def label_map(code: str) -> Dict[str, str]:
    """
    获取字典的 key->label 映射。
    使用 lru_cache 缓存，写操作后 cache_clear()。
    """
    items_dict = items(code, include_disabled=True)
    return {item["key"]: item["label"] for item in items_dict}


def items(code: str, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """
    获取字典项列表。
    
    Args:
        code: 字典代码
        include_disabled: 是否包含禁用项
        
    Returns:
        字典项列表，每个项包含 key/label/sort/enabled/used
    """
    try:
        with db_conn() as conn:
            # 尝试从数据库获取
            if include_disabled:
                rows = conn.execute(
                    "SELECT key, label, sort, enabled, used FROM dict_items WHERE dict_code = ?",
                    (code,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, label, sort, enabled, used FROM dict_items WHERE dict_code = ? AND enabled = 1",
                    (code,)
                ).fetchall()
            
            # 如果数据库中没有数据，降级到种子数据
            if not rows:
                raise sqlite3.OperationalError("no such table")
                
            return [
                {
                    "key": row["key"],
                    "label": row["label"],
                    "sort": row["sort"],
                    "enabled": bool(row["enabled"]),
                    "used": row["used"]
                }
                for row in rows
            ]
    except (sqlite3.OperationalError, sqlite3.Error):
        # 数据库访问失败或表不存在，使用种子数据
        seed_data = DICT_SEEDS.get(code, [])
        if include_disabled:
            return seed_data
        else:
            return [item for item in seed_data if item["enabled"]]


def validate(code: str, key: str) -> bool:
    """
    验证字典项是否存在且启用。
    
    Args:
        code: 字典代码
        key: 字典项 key
        
    Returns:
        是否有效
    """
    try:
        with db_conn() as conn:
            result = conn.execute(
                "SELECT 1 FROM dict_items WHERE dict_code = ? AND key = ? AND enabled = 1",
                (code, key)
            ).fetchone()
            return result is not None
    except (sqlite3.OperationalError, sqlite3.Error):
        # 数据库访问失败或表不存在，检查种子数据
        seed_data = DICT_SEEDS.get(code, [])
        return any(item["key"] == key and item["enabled"] for item in seed_data)


def used_count(code: str, key: str) -> int:
    """
    统计某个字典项在数据库中的使用次数。
    
    Args:
        code: 字典代码
        key: 字典项 key
        
    Returns:
        使用次数
    """
    try:
        with db_conn() as conn:
            # 获取字典注册表中的 table 字段，解析出要统计的列
            registry_entry = DICT_REGISTRY.get(code)
            if not registry_entry:
                return 0
                
            tables = registry_entry["table"].split(",")
            table_columns = []
            for table_col in tables:
                table_col = table_col.strip()
                if "." in table_col:
                    table, col = table_col.split(".", 1)
                    table_columns.append((table, col))
            
            # 统计每个表中使用该 key 的记录数
            total_count = 0
            for table, col in table_columns:
                try:
                    # 构造统计查询
                    count_query = f"SELECT COUNT(*) FROM {table} WHERE {col} = ?"
                    count = conn.execute(count_query, (key,)).fetchone()[0]
                    total_count += count
                except Exception:
                    # 如果表或列不存在，跳过该统计
                    continue
                    
            return total_count
    except (sqlite3.OperationalError, sqlite3.Error):
        # 数据库访问失败或表不存在，返回 0
        return 0


def level(code: str) -> str:
    """
    获取字典的级别。
    
    Args:
        code: 字典代码
        
    Returns:
        字典级别 (A/B/C/D)
    """
    registry_entry = DICT_REGISTRY.get(code)
    return registry_entry.get("level", "D") if registry_entry else "D"


# ---------------- 字典项管理函数（供后续实现）----------------

def create_item(code: str, item_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建字典项（仅 A 类）"""
    # 实现逻辑将在后续完成
    pass


def update_item(code: str, key: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
    """更新字典项（仅 A/B/C 类）"""
    # 实现逻辑将在后续完成
    pass


def delete_item(code: str, key: str) -> bool:
    """删除字典项（仅 A 类且 used=0）"""
    # 实现逻辑将在后续完成
    pass