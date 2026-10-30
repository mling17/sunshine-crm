"""CRM V2 枚举常量。

所有枚举都使用英文小写蛇形命名，中文只出现在 *_LABELS 与出参 *_label 字段。
"""
from typing import Literal, Dict


# ---------------- 客户类型 ----------------
CUSTOMER_TYPE = Literal["personal", "company"]
CUSTOMER_TYPE_LABELS: Dict[str, str] = {
    "personal": "个人",
    "company": "公司",
}


# ---------------- 线索状态 ----------------
LEAD_STATUS = Literal["new", "following", "converted", "invalid"]
LEAD_STATUS_LABELS: Dict[str, str] = {
    "new": "新线索",
    "following": "跟进中",
    "converted": "已转化",
    "invalid": "已失效",
}


# ---------------- 线索失效原因 ----------------
LEAD_INVALID_REASON = Literal[
    "invalid_phone", "blacklist", "no_intent", "duplicate", "other"
]
LEAD_INVALID_REASON_LABELS: Dict[str, str] = {
    "invalid_phone": "无效号码",
    "blacklist": "黑名单",
    "no_intent": "无意向",
    "duplicate": "重复",
    "other": "其他",
}


# ---------------- 来源 ----------------
SOURCE = Literal[
    "wechat", "phone", "referral", "existing", "stock", "other"
]
SOURCE_LABELS: Dict[str, str] = {
    "wechat": "微信",
    "phone": "电话",
    "referral": "转介绍",
    "existing": "老客户",
    "stock": "存量",
    "other": "其他",
}


# ---------------- 意向等级 ----------------
INTENT_LEVEL = Literal["high", "medium", "low", "none"]
INTENT_LEVEL_LABELS: Dict[str, str] = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "none": "无意向",
}


# ---------------- 商机阶段 ----------------
DEAL_STAGE = Literal["confirm", "quote", "negotiate", "won", "lost"]
DEAL_STAGE_LABELS: Dict[str, str] = {
    "confirm": "需求确认",
    "quote": "报价",
    "negotiate": "成交洽谈",
    "won": "赢单",
    "lost": "流失",
}


# ---------------- 商机流失原因 ----------------
DEAL_LOST_REASON = Literal["price", "competitor", "give_up", "budget", "other"]
DEAL_LOST_REASON_LABELS: Dict[str, str] = {
    "price": "价格",
    "competitor": "竞品",
    "give_up": "客户放弃",
    "budget": "预算不足",
    "other": "其他",
}


# ---------------- 订单状态 ----------------
ORDER_STATUS = Literal[
    "pending_payment", "deposit_paid", "producing", "balance_paid",
    "ready_to_ship", "shipped", "completed"
]
ORDER_STATUS_LABELS: Dict[str, str] = {
    "pending_payment": "待支付",
    "deposit_paid": "已支付押金",
    "producing": "生产中",
    "balance_paid": "已支付尾款",
    "ready_to_ship": "待发货",
    "shipped": "已发货",
    "completed": "已完成",
}


# ---------------- 物流方式 ----------------
LOGISTICS_MODE = Literal["carrier", "self"]
LOGISTICS_MODE_LABELS: Dict[str, str] = {
    "carrier": "物流公司",
    "self": "自送",
}


# ---------------- 售后类型 ----------------
AFTERSALE_TYPE = Literal["return", "exchange", "repair", "complaint", "other"]
AFTERSALE_TYPE_LABELS: Dict[str, str] = {
    "return": "退货",
    "exchange": "换货",
    "repair": "维修",
    "complaint": "投诉",
    "other": "其他",
}


# ---------------- 售后状态 ----------------
AFTERSALE_STATUS = Literal["pending", "processing", "done", "rejected"]
AFTERSALE_STATUS_LABELS: Dict[str, str] = {
    "pending": "待处理",
    "processing": "处理中",
    "done": "已完成",
    "rejected": "已拒绝",
}


# ---------------- 跟进对象类型 ----------------
FOLLOW_OBJECT = Literal["lead", "customer", "deal", "order", "aftersale"]
FOLLOW_OBJECT_LABELS: Dict[str, str] = {
    "lead": "线索",
    "customer": "客户",
    "deal": "商机",
    "order": "订单",
    "aftersale": "售后",
}


# ---------------- 跟进方式 ----------------
FOLLOW_METHOD = Literal["phone", "wechat", "visit", "online"]
FOLLOW_METHOD_LABELS: Dict[str, str] = {
    "phone": "电话",
    "wechat": "微信",
    "visit": "到面",
    "online": "线上",
}


# ---------------- 附件对象类型 ----------------
ATTACH_OBJECT = Literal["follow_up", "order_payment", "aftersale"]
ATTACH_OBJECT_LABELS: Dict[str, str] = {
    "follow_up": "跟进照片",
    "order_payment": "支付截图",
    "aftersale": "售后凭证",
}


# ---------------- 客户生命周期 ----------------
CUSTOMER_LIFECYCLE = Literal["potential", "dealing", "won", "repeat"]
CUSTOMER_LIFECYCLE_LABELS: Dict[str, str] = {
    "potential": "潜在客户",
    "dealing": "商机中",
    "won": "已成交",
    "repeat": "复购",
}


# ---------------- 订单状态流 ----------------
ORDER_FLOW: Dict[str, str | None] = {
    "pending_payment": "deposit_paid",
    "deposit_paid": "producing",
    "producing": "balance_paid",
    "balance_paid": "ready_to_ship",
    "ready_to_ship": "shipped",
    "shipped": "completed",
    "completed": None,
}


# ---------------- 售后单 SLA 天数 ----------------
AFTERSALE_SLA_DAYS = 3


# ---------------- 旧阶段映射 ----------------
LEGACY_STAGE_MAP: Dict[str, str] = {
    "lead": "confirm",
    "quoted": "quote",
    "confirmed": "negotiate",
    "deposit": "negotiate",
    "producing": "negotiate",
    "balance": "negotiate",
    "shipped": "negotiate",
    "won": "won",
    "lost": "lost",
}