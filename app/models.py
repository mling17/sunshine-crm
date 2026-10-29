"""Pydantic 入参/出参模型 + 业务枚举常量。

``STAGES`` 是商机阶段的**唯一来源**：阶段名要改（用户后续可能调整）只动
``STAGE_LABELS``，校验/展示逻辑都从它派生，不散落到各 router。前端下拉另存一份映射。
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field, model_validator

# 阶段枚举：贴合她的真实工作流（不做测量/安装）
STAGE_LABELS: dict[str, str] = {
    "lead": "线索",
    "quoted": "已报价",
    "confirmed": "客户确认",
    "deposit": "已收定金",
    "producing": "已下单生产",
    "balance": "待付尾款",
    "shipped": "已发货",
    "won": "已成交",
    "lost": "已流失",  # 旁路
}
STAGES: tuple[str, ...] = tuple(STAGE_LABELS)
DEFAULT_STAGE = "lead"


# ---------------- 字段清洗 ----------------


def _strip_name(value: object) -> str:
    """姓名去首尾空格，空串直接判非法（避免建出无名客户）。"""
    if not isinstance(value, str):
        raise ValueError("name 必须是字符串")
    value = value.strip()
    if not value:
        raise ValueError("name 不能为空")
    return value


def _blank_to_none(value: object) -> object:
    """可选文本：去空格，空串归一成 None，避免库里出现 \"\" / \"  \" 两种空值。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


CleanName = Annotated[str, BeforeValidator(_strip_name)]
OptionalText = Annotated[Optional[str], BeforeValidator(_blank_to_none)]
TagName = Annotated[str, Field(max_length=32)]

#: 标签数量上限（防止误粘贴一长串）
MAX_TAGS = 20


# ---------------- 客户 ----------------


class CustomerIn(BaseModel):
    """新建客户。"""

    name: CleanName = Field(min_length=1, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    location: OptionalText = Field(default=None, max_length=200)
    house_note: OptionalText = Field(default=None, max_length=500)
    tags: list[TagName] = Field(default_factory=list, max_length=MAX_TAGS)


class CustomerUpdate(BaseModel):
    """改客户：只改传来的字段（其余保持原值）。"""

    name: Optional[CleanName] = Field(default=None, min_length=1, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    location: OptionalText = Field(default=None, max_length=200)
    house_note: OptionalText = Field(default=None, max_length=500)
    # None = 不改标签；[] = 清空标签
    tags: Optional[list[TagName]] = Field(default=None, max_length=MAX_TAGS)


class CustomerOut(BaseModel):
    id: int
    name: str
    phone: str | None = None
    wechat: str | None = None
    location: str | None = None
    house_note: str | None = None
    created_at: str
    updated_at: str
    tags: list[str] = Field(default_factory=list)
    # 复购口径（只展示，不自动写标签）
    deals_total: int = 0
    total_closed_amount: float = 0.0
    is_repeat: bool = False

    @model_validator(mode="after")
    def _fill_is_repeat(self) -> "CustomerOut":
        """老客口径：名下累计 ≥2 单（不论成交与否），只做展示、不写 tag。"""
        self.is_repeat = self.deals_total >= 2
        return self


class CustomerListOut(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    size: int


# ---------------- 商机 ----------------


class DealOut(BaseModel):
    id: int
    customer_id: int
    product_type: str | None = None
    model: str | None = None
    spec: str | None = None
    amount: float = 0.0
    deposit: float = 0.0
    balance: float = 0.0
    stage: str
    stage_label: str | None = None
    closed_at: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _fill_stage_label(self) -> "DealOut":
        if self.stage_label is None:
            self.stage_label = STAGE_LABELS.get(self.stage)
        return self


# ---------------- 跟进 ----------------


class FollowUpOut(BaseModel):
    id: int
    customer_id: int
    deal_id: int | None = None
    content: str
    next_date: str | None = None
    created_at: str


class CustomerDetailOut(CustomerOut):
    """客户详情：档案 + 其下商机 + 最近跟进（T5 之后跟进会变多，只回最近 20 条）。"""

    deals: list[DealOut] = Field(default_factory=list)
    follow_ups: list[FollowUpOut] = Field(default_factory=list)
