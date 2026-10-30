"""Pydantic 入参/出参模型 + 业务枚举常量。

所有枚举统一从 app/enums.py 导入，确保一致性。
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.enums import (
    DEAL_STAGE,
    DEAL_STAGE_LABELS,
    CUSTOMER_TYPE,
    CUSTOMER_TYPE_LABELS,
    SOURCE,
    SOURCE_LABELS,
    INTENT_LEVEL,
    INTENT_LEVEL_LABELS,
    LEAD_STATUS,
    LEAD_STATUS_LABELS,
    LEAD_INVALID_REASON,
    LEAD_INVALID_REASON_LABELS,
    DEAL_LOST_REASON,
    DEAL_LOST_REASON_LABELS,
    ORDER_STATUS,
    ORDER_STATUS_LABELS,
    LOGISTICS_MODE,
    LOGISTICS_MODE_LABELS,
    AFTERSALE_TYPE,
    AFTERSALE_TYPE_LABELS,
    AFTERSALE_STATUS,
    AFTERSALE_STATUS_LABELS,
    FOLLOW_OBJECT,
    FOLLOW_OBJECT_LABELS,
    FOLLOW_METHOD,
    FOLLOW_METHOD_LABELS,
    ATTACH_OBJECT,
    ATTACH_OBJECT_LABELS,
    CUSTOMER_LIFECYCLE,
    CUSTOMER_LIFECYCLE_LABELS,
)

# 商机阶段枚举
STAGE_LABELS = DEAL_STAGE_LABELS
STAGES = tuple(DEAL_STAGE_LABELS.keys())
DEFAULT_STAGE = "confirm"  # V2 默认阶段改为 confirm


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


class AttachmentOut(BaseModel):
    """一张照片的元数据；``url`` 是**后端**路径（前端拼 ``/crm`` 前缀即可）。"""

    id: int
    follow_up_id: int | None = None
    file_name: str | None = None
    mime_type: str | None = None
    size: int = 0
    url: str


class FollowUpItemOut(FollowUpOut):
    """跟进列表项：带客户名 / 商机阶段 / 照片（列表页要显示“📷 N”）。"""

    customer_name: str | None = None
    deal_stage: str | None = None
    photo_count: int = 0
    photos: list[AttachmentOut] = Field(default_factory=list)


#: 一条跟进最多几张照片（应用层上限，DDL 里没有 CHECK 约束）
MAX_PHOTOS = 3


class CustomerDetailOut(CustomerOut):
    """客户详情：档案 + 其下商机 + 最近跟进（T5 之后跟进会变多，只回最近 20 条）。"""

    deals: list[DealOut] = Field(default_factory=list)
    follow_ups: list[FollowUpOut] = Field(default_factory=list)


# ---------------- 商机入参 ----------------


class DealIn(BaseModel):
    """新建商机。``amount`` 必填，deposit/balance 先只写不用，默认 0。"""

    customer_id: int = Field(gt=0)
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: OptionalText = Field(default=None, max_length=200)
    amount: float = Field(ge=0)
    deposit: float = Field(default=0, ge=0)
    balance: float = Field(default=0, ge=0)
    stage: str = Field(default=DEFAULT_STAGE, max_length=32)


class DealUpdate(BaseModel):
    """改商机：只改传来的字段。``amount``/``stage`` 显式传 null 会在路由层被 400 拒绝。"""

    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: OptionalText = Field(default=None, max_length=200)
    amount: float | None = Field(default=None, ge=0)
    deposit: float | None = Field(default=None, ge=0)
    balance: float | None = Field(default=None, ge=0)
    stage: str | None = Field(default=None, max_length=32)


# ---------------- 看板 / 统计 ----------------


class TodayFollowUpOut(BaseModel):
    """今日待跟进的一条（``days_overdue`` 由 SQL 按天差算，0=今天到期）。"""

    id: int
    customer_id: int
    customer_name: str
    deal_id: int | None = None
    deal_stage: str | None = None
    deal_stage_label: str | None = None
    content: str
    next_date: str
    days_overdue: int = 0


class MonthWonOut(BaseModel):
    count: int = 0
    amount: float = 0.0


class DashboardStatsOut(BaseModel):
    customers_total: int = 0
    deals_by_stage: dict[str, int] = Field(default_factory=dict)
    month_new_customers: int = 0
    repeat_customers: int = 0
    month_won: MonthWonOut = Field(default_factory=MonthWonOut)


class DashboardOut(BaseModel):
    today_followups: list[TodayFollowUpOut] = Field(default_factory=list)
    month_won: MonthWonOut = Field(default_factory=MonthWonOut)
    stats: DashboardStatsOut = Field(default_factory=DashboardStatsOut)


# ---------------- CSV 导入 ----------------


class ImportFieldOut(BaseModel):
    """系统可接收的字段（前端映射下拉用）。"""

    key: str
    label: str
    required: bool = False


class ImportPreviewOut(BaseModel):
    ok: bool = True
    #: csv = 解析成功；xlsx_unsupported = 收到 Excel，提示先另存为 CSV（不报错）
    kind: str = "csv"
    file_name: str = ""
    #: 预览缓存 token，commit 时回传（file_ref），免二次上传
    file_ref: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    headers: list[str] = Field(default_factory=list)
    preview: list[dict[str, str]] = Field(default_factory=list)
    total_rows: int = 0
    suggested_mapping: dict[str, str] = Field(default_factory=dict)
    last_mapping: dict[str, str] | None = None
    system_fields: list[ImportFieldOut] = Field(default_factory=list)
    message: str = ""


class ImportCommitIn(BaseModel):
    """JSON 方式的 commit（multipart 方式由路由单独解析）。"""

    file_ref: str | None = None
    column_mapping: dict[str, str] | None = None
    source_name: str | None = None


class ImportCommitOut(BaseModel):
    ok: bool = True
    imported: int = 0
    skipped: int = 0
    total_rows: int = 0
    import_log_id: int
    mapping_used: dict[str, str] = Field(default_factory=dict)
    mapping_reused: bool = False
    source_name: str = ""
