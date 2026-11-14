"""Pydantic 入参/出参模型 + 业务枚举常量。

所有枚举统一从 app/enums.py 导入，确保一致性。
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app import labels
from app.enums import (
    DEAL_STAGE,
    DEAL_STAGE_LABELS,
    DEAL_STAGE_ORDER,
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
STAGES = DEAL_STAGE_ORDER
DEFAULT_STAGE = "quote"  # PLANNER-V3 §1.1：新建商机默认「报价」（阶段顺序 报价→待客户确认→成交/流失）


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


def normalize_spec(value: object) -> object:
    """尺寸/洞口尺寸落库统一使用 ``*`` 作为宽高分隔符。"""
    value = _blank_to_none(value)
    if not isinstance(value, str):
        return value
    return value.replace("x", "*").replace("X", "*").replace("×", "*")


CleanName = Annotated[str, BeforeValidator(_strip_name)]
OptionalText = Annotated[Optional[str], BeforeValidator(_blank_to_none)]
SpecText = Annotated[Optional[str], BeforeValidator(normalize_spec)]
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
    note: OptionalText = Field(default=None, max_length=500)
    customer_type: CUSTOMER_TYPE = Field(default="personal")
    source: OptionalText = Field(default=None, max_length=32)
    source_other: OptionalText = Field(default=None, max_length=100)
    intent_level: OptionalText = Field(default=None, max_length=32)
    company_name: OptionalText = Field(default=None, max_length=100)
    owner: OptionalText = Field(default=None, max_length=32)
    tags: list[TagName] = Field(default_factory=list, max_length=MAX_TAGS)


class CustomerUpdate(BaseModel):
    """改客户：只改传来的字段（其余保持原值）。"""

    name: Optional[CleanName] = Field(default=None, min_length=1, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    location: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)
    customer_type: CUSTOMER_TYPE | None = None
    source: OptionalText = Field(default=None, max_length=32)
    source_other: OptionalText = Field(default=None, max_length=100)
    intent_level: OptionalText = Field(default=None, max_length=32)
    company_name: OptionalText = Field(default=None, max_length=100)
    owner: OptionalText = Field(default=None, max_length=32)
    # None = 不改标签；[] = 清空标签
    tags: Optional[list[TagName]] = Field(default=None, max_length=MAX_TAGS)


class CustomerOut(BaseModel):
    id: int
    name: str
    phone: str | None = None
    wechat: str | None = None
    location: str | None = None
    note: str | None = None
    customer_type: str | None = None
    source: str | None = None
    source_other: str | None = None
    intent_level: str | None = None
    #: 公司客户的联系人姓名；个人客户通常为空。
    company_name: str | None = None
    owner: str | None = None
    created_at: str
    updated_at: str
    tags: list[str] = Field(default_factory=list)
    # 复购口径（只展示，不自动写标签）
    deals_total: int = 0
    orders_total: int = 0
    total_closed_amount: float = 0.0
    is_repeat: bool = False
    # 中文显示名（走数据字典，改名即生效）
    source_label: str | None = None
    customer_type_label: str | None = None
    intent_level_label: str | None = None

    @model_validator(mode="after")
    def _fill_labels(self) -> "CustomerOut":
        if self.source_label is None:
            self.source_label = labels.source(self.source) if self.source != "other" else (self.source_other or "其他")
        if self.customer_type_label is None:
            self.customer_type_label = labels.customer_type(self.customer_type)
        if self.intent_level_label is None:
            self.intent_level_label = labels.intent_level(self.intent_level)
        return self

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


class ProductIn(BaseModel):
    """产品主档新建。产品参数由业务维护，规格范围不等于客户成交尺寸。"""

    #: 新建时由服务端分配，兼容旧客户端仍可传 code，但不会采用传入值。
    code: OptionalText = Field(default=None, max_length=64)
    name: CleanName = Field(min_length=1, max_length=120)
    category: str = Field(default="天窗", min_length=1, max_length=32)
    series: OptionalText = Field(default=None, max_length=32)
    structure: OptionalText = Field(default=None, max_length=32)
    opening_mode: OptionalText = Field(default=None, max_length=32)
    drive_type: OptionalText = Field(default=None, max_length=16)
    frame_type: OptionalText = Field(default=None, max_length=32)
    leaf_type: OptionalText = Field(default=None, max_length=32)
    edge_type: OptionalText = Field(default=None, max_length=16)
    leaf_count: Optional[int] = Field(default=None, ge=1, le=30)
    min_width: Optional[float] = Field(default=None, ge=0)
    max_width: Optional[float] = Field(default=None, ge=0)
    min_height: Optional[float] = Field(default=None, ge=0)
    max_height: Optional[float] = Field(default=None, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_template: OptionalText = Field(default=None, max_length=300)
    description: OptionalText = Field(default=None, max_length=1000)
    is_active: bool = True


class ProductImportPreview(BaseModel):
    """上传下单表后返回的识别结果；预览阶段不写入产品主档。"""

    code: str
    duplicate_product_id: int | None = None
    duplicate_product_code: str | None = None
    name: str
    category: str
    series: str | None = None
    structure: str | None = None
    opening_mode: str | None = None
    drive_type: str | None = None
    frame_type: str | None = None
    leaf_type: str | None = None
    edge_type: str | None = None
    leaf_count: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_template: str | None = None
    description: str | None = None
    config_summary: str = ""
    form_file_name: str
    form_file_size: int
    warnings: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    """产品主档部分更新。"""

    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[CleanName] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, min_length=1, max_length=32)
    series: OptionalText = Field(default=None, max_length=32)
    structure: OptionalText = Field(default=None, max_length=32)
    opening_mode: OptionalText = Field(default=None, max_length=32)
    drive_type: OptionalText = Field(default=None, max_length=16)
    frame_type: OptionalText = Field(default=None, max_length=32)
    leaf_type: OptionalText = Field(default=None, max_length=32)
    edge_type: OptionalText = Field(default=None, max_length=16)
    leaf_count: Optional[int] = Field(default=None, ge=1, le=30)
    min_width: Optional[float] = Field(default=None, ge=0)
    max_width: Optional[float] = Field(default=None, ge=0)
    min_height: Optional[float] = Field(default=None, ge=0)
    max_height: Optional[float] = Field(default=None, ge=0)
    attributes: dict[str, Any] | None = None
    source_template: OptionalText = Field(default=None, max_length=300)
    description: OptionalText = Field(default=None, max_length=1000)
    is_active: bool | None = None


class ProductOut(BaseModel):
    id: int
    code: str
    name: str
    category: str
    series: str | None = None
    structure: str | None = None
    opening_mode: str | None = None
    drive_type: str | None = None
    frame_type: str | None = None
    leaf_type: str | None = None
    edge_type: str | None = None
    leaf_count: int | None = None
    min_width: float | None = None
    max_width: float | None = None
    min_height: float | None = None
    max_height: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_template: str | None = None
    form_file_name: str | None = None
    form_file_size: int = 0
    form_sha256: str | None = None
    form_available: bool = False
    description: str | None = None
    is_active: bool = True
    config_summary: str = ""
    deal_count: int = 0
    order_count: int = 0
    created_at: str
    updated_at: str


class ProductDetailOut(ProductOut):
    deals: list[dict] = Field(default_factory=list)


class DealItemIn(BaseModel):
    """商机产品明细：同产品同参数用 quantity，参数不同必须拆行。"""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=999)
    spec: SpecText = Field(default=None, max_length=200)
    production_spec: OptionalText = Field(default=None, max_length=1000)
    unit_price: float = Field(ge=0)
    drive_type: OptionalText = Field(default=None, max_length=32)
    note: OptionalText = Field(default=None, max_length=500)


class DealItemUpdate(BaseModel):
    """修改一条商机产品明细；未传字段保持原值。"""

    model_config = ConfigDict(extra="forbid")

    product_id: int | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, ge=1, le=999)
    spec: SpecText = Field(default=None, max_length=200)
    production_spec: OptionalText = Field(default=None, max_length=1000)
    unit_price: float | None = Field(default=None, ge=0)
    drive_type: OptionalText = Field(default=None, max_length=32)
    note: OptionalText = Field(default=None, max_length=500)


class DealItemOut(BaseModel):
    id: int
    deal_id: int
    product_id: int | None = None
    product_code_snapshot: str | None = None
    product_name_snapshot: str | None = None
    product_config_snapshot: str | None = None
    product_type: str | None = None
    model: str | None = None
    drive_type: str | None = None
    drive_type_label: str | None = None
    quantity: int = 1
    spec: str | None = None
    production_spec: str | None = None
    unit_price: float = 0.0
    amount: float = 0.0
    note: str | None = None
    sort: int = 0
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _fill_drive_label(self) -> "DealItemOut":
        if self.drive_type_label is None and self.drive_type:
            self.drive_type_label = labels.drive_type(self.drive_type)
        return self


class QuoteIn(BaseModel):
    """新建报价单：产品与下单表在报价单内继续维护。"""

    model_config = ConfigDict(extra="forbid")

    title: OptionalText = Field(default=None, max_length=120)
    note: OptionalText = Field(default=None, max_length=1000)


class QuoteItemOut(BaseModel):
    id: int
    quote_id: int
    product_id: int
    product_code_snapshot: str | None = None
    product_name_snapshot: str | None = None
    product_config_snapshot: str | None = None
    product_type: str | None = None
    model: str | None = None
    drive_type: str | None = None
    drive_type_label: str | None = None
    quantity: int = 1
    spec: str | None = None
    production_spec: str | None = None
    unit_price: float = 0.0
    amount: float = 0.0
    note: str | None = None
    form_file_name: str | None = None
    form_file_size: int = 0
    form_available: bool = False
    recognized_total: float = 0.0
    a1_value: str | None = None
    form_content: dict = Field(default_factory=dict)
    template_url: str | None = None
    form_url: str | None = None
    form_preview_url: str | None = None
    sort: int = 0
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _fill_drive_label(self) -> "QuoteItemOut":
        if self.drive_type_label is None and self.drive_type:
            self.drive_type_label = labels.drive_type(self.drive_type)
        return self


class QuoteOut(BaseModel):
    id: int
    quote_no: str
    deal_id: int
    customer_id: int
    title: str
    note: str | None = None
    status: str
    status_label: str | None = None
    amount: float = 0.0
    confirmed_at: str | None = None
    confirmation_note: str | None = None
    order_id: int | None = None
    order_no: str | None = None
    items: list[QuoteItemOut] = Field(default_factory=list)
    confirmation_files: list["AttachmentOut"] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _fill_status_label(self) -> "QuoteOut":
        if self.status_label is None:
            from app.enums import QUOTE_STATUS_LABELS

            self.status_label = QUOTE_STATUS_LABELS.get(self.status, self.status)
        return self


class DealTagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TagName = Field(min_length=1, max_length=32)


class DealTagOut(BaseModel):
    id: int
    name: str
    source: Literal["auto", "manual"]
    deletable: bool


class DealOut(BaseModel):
    id: int
    customer_id: int
    product_type: str | None = None
    model: str | None = None
    product_id: int | None = None
    product_code_snapshot: str | None = None
    product_name_snapshot: str | None = None
    product_config_snapshot: str | None = None
    spec: str | None = None
    amount: float = 0.0
    deposit: float = 0.0
    balance: float = 0.0
    stage: str
    stage_label: str | None = None
    lost_reason: str | None = None
    lost_reason_other: str | None = None
    lost_reason_label: str | None = None
    source_lost_deal_id: int | None = None
    order_id: int | None = None
    owner: str | None = None
    closed_at: str | None = None
    created_at: str
    updated_at: str
    drive_type: str | None = None
    drive_type_label: str | None = None
    note: str | None = None
    #: 已生成订单 → 基本信息冻结（PLANNER-V3 §6.2）
    locked: bool = False
    locked_at: str | None = None
    quote_count: int = 0
    confirmed_quote_no: str | None = None

    @model_validator(mode="after")
    def _fill_stage_label(self) -> "DealOut":
        if self.order_id is not None:
            self.stage_label = "已生成订单"
        elif self.stage_label is None:
            self.stage_label = labels.deal_stage(self.stage)
        return self

    @model_validator(mode="after")
    def _fill_lost_reason_label(self) -> "DealOut":
        if self.lost_reason_label is None and self.lost_reason:
            self.lost_reason_label = labels.lost_reason(self.lost_reason)
        return self

    @model_validator(mode="after")
    def _fill_drive_type_label(self) -> "DealOut":
        if self.drive_type_label is None and self.drive_type:
            self.drive_type_label = labels.drive_type(self.drive_type)
        return self


class DealDetailOut(DealOut):
    """商机详情：+ 客户名 / 订单 / 履历 / 资料汇总（PLANNER-V3 §5.5）。"""

    customer_name: str | None = None
    order_no: str | None = None
    #: 履历（跟进 + 编辑 + 阶段变更 + 生成订单 + 订单事件），倒序
    timeline: list[dict] = Field(default_factory=list)
    #: 资料汇总卡：所有跟进附件
    materials: list[dict] = Field(default_factory=list)
    order: dict | None = None
    items: list[DealItemOut] = Field(default_factory=list)
    quotes: list[QuoteOut] = Field(default_factory=list)
    tags: list[DealTagOut] = Field(default_factory=list)


# ---------------- 跟进 ----------------


class FollowPhraseIn(BaseModel):
    """常用短语：同一内容可分别用于不同业务对象。"""

    model_config = ConfigDict(extra="forbid")

    object_type: Literal["lead", "customer", "deal", "order", "aftersale"]
    content: str = Field(min_length=1, max_length=200)


class FollowPhraseOut(BaseModel):
    id: int
    object_type: str
    content: str
    sort: int = 0
    created_at: str


class FollowUpOut(BaseModel):
    id: int
    customer_id: int | None = None
    deal_id: int | None = None
    quote_id: int | None = None
    quote_no: str | None = None
    quote_title: str | None = None
    object_type: str | None = None
    object_id: int | None = None
    method: str | None = None
    #: 方式中文（走数据字典 follow_method）
    method_label: str | None = None
    #: follow=人工跟进；create/change/stage/order/aftersale/pay/ship=系统履历
    kind: str | None = None
    content: str
    detail: dict | None = None
    next_date: str | None = None
    created_by: int | None = None
    created_at: str


class AttachmentOut(BaseModel):
    """一张照片的元数据；``url`` 是**后端**路径（前端拼 ``/crm`` 前缀即可）。"""

    id: int
    follow_up_id: int | None = None
    file_name: str | None = None
    mime_type: str | None = None
    size: int = 0
    url: str
    method_label: str | None = None


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
    orders: list[dict] = Field(default_factory=list)
    aftersales: list[dict] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


# ---------------- 商机入参 ----------------


class DealIn(BaseModel):
    """新建商机。新流程只要求客户和备注；产品在报价单中维护。"""

    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    product_id: int | None = Field(default=None, gt=0)
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: SpecText = Field(default=None, max_length=200)
    amount: float = Field(default=0, ge=0)
    stage: str = Field(default=DEFAULT_STAGE, max_length=32)
    #: 手动/电动 —— 必填由路由层给业务错误码（drive_type_required），不在 pydantic 层拦
    drive_type: OptionalText = Field(default=None, max_length=32)
    note: OptionalText = Field(default=None, max_length=500)


class DealUpdate(BaseModel):
    """改商机：只改传来的字段。``amount``/``stage`` 显式传 null 会在路由层被 400 拒绝。"""

    model_config = ConfigDict(extra="forbid")

    product_id: int | None = Field(default=None, gt=0)
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: SpecText = Field(default=None, max_length=200)
    amount: float | None = Field(default=None, ge=0)
    stage: str | None = Field(default=None, max_length=32)
    drive_type: str | None = Field(default=None, max_length=32)
    note: OptionalText = Field(default=None, max_length=500)


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
    last_follow_at: str | None = None
    intent_level: str | None = None
    customer_type: str | None = None


class MonthWonOut(BaseModel):
    count: int = 0
    amount: float = 0.0


class DashboardStatsOut(BaseModel):
    customers_total: int = 0
    #: 进行中商机（非成交/流失）
    in_progress_deals: dict = Field(default_factory=dict)
    #: 最近动态 10 条（跟进 + 订单事件混排）
    recent_activities: list[dict] = Field(default_factory=list)
    deals_by_stage: dict[str, int] = Field(default_factory=dict)
    month_new_customers: int = 0
    repeat_customers: int = 0
    month_won: MonthWonOut = Field(default_factory=MonthWonOut)
    orders_by_status: dict[str, dict[str, int | float]] = Field(default_factory=dict)
    recent_orders: list[dict] = Field(default_factory=list)
    aftersale_sla_alerts: list[dict] = Field(default_factory=list)
    #: 今日各业务对象的新增数与跟进次数（工作台“今日工作统计”）
    today_activity: list[dict] = Field(default_factory=list)
    #: 昨日各业务对象的新增数与跟进次数（工作台“昨日新增与跟进”）
    yesterday_activity: list[dict] = Field(default_factory=list)
    #: 未完成售后单准确数量（工作台“进行中售后”）
    active_aftersales_count: int = 0
    #: 最近未完成售后单（工作台售后提醒区，最多 4 条）
    recent_aftersales: list[dict] = Field(default_factory=list)


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
    #: 导入目标固定为线索池；客户必须由线索转化创建。
    target: str = "leads"


class ImportCommitOut(BaseModel):
    ok: bool = True
    imported: int = 0
    skipped: int = 0
    total_rows: int = 0
    import_log_id: int
    mapping_used: dict[str, str] = Field(default_factory=dict)
    mapping_reused: bool = False
    source_name: str = ""


# ---------------- 线索 ----------------


class LeadIn(BaseModel):
    """新建线索。"""

    name: Optional[CleanName] = Field(default=None, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    lead_type: CUSTOMER_TYPE = Field(default="personal")
    company_name: OptionalText = Field(default=None, max_length=100)
    #: 来源取数据字典 customer_source（A 级可自由增删），不能用 Literal 锁死
    source: str = Field(min_length=1, max_length=32)
    source_other: OptionalText = Field(default=None, max_length=100)
    location: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)
    intent_level: OptionalText = Field(default=None, max_length=32)
    owner: OptionalText = Field(default=None, max_length=32)
    tags: list[TagName] = Field(default_factory=list, max_length=MAX_TAGS)


class LeadUpdate(BaseModel):
    """改线索：只改传来的字段（其余保持原值）。"""

    name: Optional[CleanName] = Field(default=None, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    lead_type: CUSTOMER_TYPE | None = None
    company_name: OptionalText = Field(default=None, max_length=100)
    source: OptionalText = Field(default=None, max_length=32)
    source_other: OptionalText = Field(default=None, max_length=100)
    location: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)
    intent_level: OptionalText = Field(default=None, max_length=32)
    owner: OptionalText = Field(default=None, max_length=32)
    # None = 不改标签；[] = 清空标签
    tags: Optional[list[TagName]] = Field(default=None, max_length=MAX_TAGS)


class LeadTagsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[TagName] = Field(default_factory=list, max_length=MAX_TAGS)


class LeadTagOut(BaseModel):
    id: int
    name: str


class LeadOut(BaseModel):
    id: int
    name: str | None = None
    phone: str | None = None
    wechat: str | None = None
    lead_type: str
    company_name: str | None = None
    source: str
    source_other: str | None = None
    location: str | None = None
    note: str | None = None
    intent_level: str | None = None
    status: str
    invalid_reason: str | None = None
    invalid_reason_other: str | None = None
    converted_customer_id: int | None = None
    converted_deal_id: int | None = None
    owner: str | None = None
    created_by: int | None = None
    tags: list[str] = Field(default_factory=list)
    duplicate_hint: dict | None = None
    created_at: str
    updated_at: str
    # 派生态（PLANNER-V3 §5.3）：最近一条真实跟进
    last_follow_at: str | None = None
    next_date: str | None = None
    days_overdue: int = 0
    intent_level_label: str | None = None


class ExternalLeadIn(BaseModel):
    """第三方新增线索；来源、状态和审计字段由服务端控制。"""

    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=1, max_length=32)
    name: Optional[CleanName] = Field(default=None, max_length=64)
    wechat: OptionalText = Field(default=None, max_length=64)
    lead_type: CUSTOMER_TYPE | None = None
    company_name: OptionalText = Field(default=None, max_length=100)
    source_other: OptionalText = Field(default=None, max_length=100)
    location: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)
    intent_level: OptionalText = Field(default=None, max_length=32)
    owner: OptionalText = Field(default=None, max_length=32)
    tags: list[TagName] = Field(default_factory=list, max_length=MAX_TAGS)


class ExternalPhoneCheckIn(BaseModel):
    """外部批量校验手机号；一次最多 500 个输入值。"""

    model_config = ConfigDict(extra="forbid")

    #: 保留原始 JSON 值，确保非字符串项也进入统一规范化和
    #: invalid_positions 错误契约，而不是提前变成通用校验错误。
    phones: list[object] = Field(min_length=1, max_length=500)


class ExternalPhoneCheckItem(BaseModel):
    phone: str
    exists: bool


class ExternalPhoneCheckOut(BaseModel):
    items: list[ExternalPhoneCheckItem]


class LeadDetailOut(LeadOut):
    """线索详情：档案 + 标签 + 跟进记录。"""

    tags: list[str] = Field(default_factory=list)
    follow_ups: list[FollowUpOut] = Field(default_factory=list)


class LeadListOut(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    size: int


class LeadConvertDeal(BaseModel):
    """转化时新建的商机（PLANNER-V3 §5.3）。

    ``drive_type``（手动/电动）必填；不再收定金/尾款；阶段固定「报价」。
    """

    title: OptionalText = Field(default=None, max_length=100)
    product_id: int | None = Field(default=None, gt=0)
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: SpecText = Field(default=None, max_length=200)
    amount: float = Field(default=0, ge=0)
    drive_type: OptionalText = Field(default=None, max_length=32)
    note: OptionalText = Field(default=None, max_length=500)
    stage: str | None = Field(default=None, max_length=32)
    owner: OptionalText = Field(default=None, max_length=32)


class LeadConvertIn(BaseModel):
    """线索转化入参。"""

    mode: Literal["new", "link"]
    force_new: bool = False
    link_customer_id: int | None = None
    deal: LeadConvertDeal


class LeadConvertOut(BaseModel):
    """线索转化出参。"""

    lead: LeadOut
    customer: CustomerOut | None = None
    deal: DealOut | None = None
    dedupe: Literal["none", "linked", "forced"]


class DuplicateHint(BaseModel):
    """重复提示对象。"""

    object_type: Literal["lead", "customer"]
    object_id: int
    name: str


class LeadConvertCheckOut(BaseModel):
    """线索转化前检查结果。"""

    has_match: bool
    matches: list[DuplicateHint] = Field(default_factory=list)


# ---------------- 订单 ----------------


class OrderIn(BaseModel):
    """新建订单。"""

    customer_id: int = Field(gt=0)
    deal_id: int = Field(gt=0)
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: SpecText = Field(default=None, max_length=200)
    amount: float = Field(ge=0)
    status: ORDER_STATUS = "pending_payment"
    owner: OptionalText = Field(default=None, max_length=32)
    # 新增字段
    paid_amount: float = Field(default=0, ge=0)
    carrier_id: Optional[int] = Field(default=None, gt=0)
    tracking_number: OptionalText = Field(default=None, max_length=64)
    created_at: str
    updated_at: str


class OrderUpdate(BaseModel):
    """更新订单自有的物流、配送和备注信息。

    商品快照、报价金额、优惠和订单来源由商机 / 报价单继承，不在这里开放修改。
    """

    model_config = ConfigDict(extra="forbid")

    order_name: OptionalText = Field(default=None, max_length=120)
    logistics_mode: LOGISTICS_MODE | None = None
    carrier_id: Optional[int] = Field(default=None, gt=0)
    carrier_contact_id: Optional[int] = Field(default=None, gt=0)
    logistics_fee: float | None = Field(default=None, ge=0)
    tracking_number: OptionalText = Field(default=None, max_length=64)
    receiver_name: OptionalText = Field(default=None, max_length=32)
    receiver_phone: OptionalText = Field(default=None, max_length=32)
    receiver_address: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)


class OrderOut(BaseModel):
    """订单列表项。"""

    id: int
    order_no: str
    order_name: str | None = None
    customer_id: int
    deal_id: int
    quote_id: int | None = None
    product_type: str | None = None
    model: str | None = None
    product_id: int | None = None
    product_code_snapshot: str | None = None
    product_name_snapshot: str | None = None
    product_config_snapshot: str | None = None
    spec: str | None = None
    amount: float = 0.0
    product_total: float = 0.0
    discount_amount: float = 0.0
    discount_reason: str | None = None
    product_payable: float = 0.0
    logistics_fee: float = 0.0
    logistics_mode: str | None = None
    logistics_mode_label: str | None = None
    item_count: int = 0
    status: str
    status_label: str | None = None
    owner: str | None = None
    paid_amount: float = 0.0
    carrier_id: int | None = None
    carrier_contact_id: int | None = None
    carrier_contact_name: str | None = None
    carrier_contact_phone: str | None = None
    tracking_number: str | None = None
    receiver_name: str | None = None
    receiver_phone: str | None = None
    receiver_address: str | None = None
    note: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="before")
    @classmethod
    def _compat_cols(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            data.setdefault("paid_amount", (data.get("deposit_paid") or 0.0) + (data.get("balance_paid") or 0.0))
            if not data.get("product_total"):
                data["product_total"] = data.get("amount") or 0.0
            if not data.get("product_payable"):
                data["product_payable"] = max(
                    0.0,
                    float(data.get("product_total") or 0.0)
                    - float(data.get("discount_amount") or 0.0),
                )
            if not data.get("freight_amount"):
                data["freight_amount"] = data.get("logistics_fee") or 0.0
            if data.get("tracking_number") is None and data.get("tracking_no") is not None:
                data["tracking_number"] = data.get("tracking_no")
        return data

    @model_validator(mode="after")
    def _fill_status_label(self) -> "OrderOut":
        if self.status_label is None:
            self.status_label = labels.order_status(self.status)
        if self.logistics_mode_label is None and self.logistics_mode:
            self.logistics_mode_label = labels.logistics_mode(self.logistics_mode)
        return self


class OrderDetailOut(BaseModel):
    """订单详情。"""

    id: int
    order_no: str
    order_name: str | None = None
    customer_id: int
    deal_id: int
    quote_id: int | None = None
    product_type: str | None = None
    model: str | None = None
    product_id: int | None = None
    product_code_snapshot: str | None = None
    product_name_snapshot: str | None = None
    product_config_snapshot: str | None = None
    spec: str | None = None
    amount: float = 0.0
    product_total: float = 0.0
    discount_amount: float = 0.0
    discount_reason: str | None = None
    product_payable: float = 0.0
    item_count: int = 0
    customer_confirmed_at: str | None = None
    customer_confirmation_note: str | None = None
    status: str
    status_label: str | None = None
    owner: str | None = None
    paid_amount: float = 0.0
    carrier_id: int | None = None
    carrier_contact_id: int | None = None
    carrier_contact_name: str | None = None
    carrier_contact_phone: str | None = None
    tracking_number: str | None = None
    created_at: str
    updated_at: str
    # 扩展字段
    status_log: list[OrderStatusLogOut] = Field(default_factory=list)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    carrier: dict | None = None
    # PLANNER-V3 §5.6：计划押金/尾款、收款拆项、配送信息、履历
    deposit_amount: float | None = None
    balance_amount: float | None = None
    deposit_paid: float = 0.0
    balance_paid: float = 0.0
    logistics_mode: str | None = None
    logistics_mode_label: str | None = None
    logistics_fee: float = 0.0
    freight_amount: float = 0.0
    address_id: int | None = None
    receiver_name: str | None = None
    receiver_phone: str | None = None
    receiver_address: str | None = None
    tracking_no: str | None = None
    note: str | None = None
    carrier_contacts: list[dict] = Field(default_factory=list)
    aftersales: list[dict] = Field(default_factory=list)
    deal: dict | None = None
    quote: dict | None = None
    timeline: list[dict] = Field(default_factory=list)
    items: list[dict] = Field(default_factory=list)
    confirmation_files: list[AttachmentOut] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _compat_cols(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            data.setdefault("paid_amount", (data.get("deposit_paid") or 0.0) + (data.get("balance_paid") or 0.0))
            if not data.get("product_total"):
                data["product_total"] = data.get("amount") or 0.0
            if not data.get("product_payable"):
                data["product_payable"] = max(
                    0.0,
                    float(data.get("product_total") or 0.0)
                    - float(data.get("discount_amount") or 0.0),
                )
            if not data.get("freight_amount"):
                data["freight_amount"] = data.get("logistics_fee") or 0.0
            if data.get("tracking_number") is None and data.get("tracking_no") is not None:
                data["tracking_number"] = data.get("tracking_no")
        return data

    @model_validator(mode="after")
    def _fill_status_label(self) -> "OrderDetailOut":
        if self.status_label is None:
            self.status_label = labels.order_status(self.status)
        if self.logistics_mode_label is None and self.logistics_mode:
            self.logistics_mode_label = labels.logistics_mode(self.logistics_mode)
        return self


class OrderStatusLogOut(BaseModel):
    """订单状态日志。"""

    id: int
    order_id: int
    from_status: str | None = None
    from_status_label: str | None = None
    to_status: str
    to_status_label: str | None = None
    event_type: str | None = None
    note: str | None = None
    created_at: str

    @model_validator(mode="after")
    def _fill_status_labels(self) -> "OrderStatusLogOut":
        if self.from_status and self.from_status_label is None:
            self.from_status_label = labels.order_status(self.from_status)
        if self.to_status_label is None:
            self.to_status_label = labels.order_status(self.to_status)
        return self


# ---------------- 物流公司 ----------------


class CarrierIn(BaseModel):
    """新建物流公司。``contacts`` = [{name, phone, tags[]}]（多联系人，可空）。"""

    name: str = Field(min_length=1, max_length=64)
    code: OptionalText = Field(default=None, max_length=32)
    contact_person: OptionalText = Field(default=None, max_length=32)
    phone: OptionalText = Field(default=None, max_length=32)
    address: OptionalText = Field(default=None, max_length=200)
    contacts: list[dict] = Field(default_factory=list)


class CarrierUpdate(BaseModel):
    """更新物流公司。传 ``contacts`` 则整组覆盖。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    code: OptionalText = Field(default=None, max_length=32)
    contact_person: OptionalText = Field(default=None, max_length=32)
    phone: OptionalText = Field(default=None, max_length=32)
    address: OptionalText = Field(default=None, max_length=200)
    contacts: list[dict] | None = None
    is_active: bool | None = None


class CarrierOut(BaseModel):
    """物流公司列表项。"""

    id: int
    name: str
    code: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    address: str | None = None
    created_at: str
    updated_at: str
    is_active: bool = True
    #: 多联系人（PLANNER-V3 §3.4）：[{id,name,phone,tags[]}]
    contacts: list[dict] = Field(default_factory=list)
    #: 被订单关联次数（实时算，不落库）
    order_count: int = 0

# ---------------- 售后 ----------------


class AftersaleIn(BaseModel):
    """新建售后单。"""

    order_id: int = Field(gt=0)
    type: str = Field(min_length=1, max_length=16)
    type_other: OptionalText = Field(default=None, max_length=64)
    description: CleanName = Field(min_length=1, max_length=1000)
    #: 可关联同一订单下已有的历史售后单。
    related_aftersale_id: int | None = Field(default=None, gt=0)


class AftersaleUpdate(BaseModel):
    """更新售后单（描述类 + 处理结果/拒绝原因）。"""

    type: Optional[str] = Field(default=None, min_length=1, max_length=16)
    type_other: OptionalText = Field(default=None, max_length=64)
    description: Optional[CleanName] = Field(default=None, min_length=1, max_length=1000)
    result: OptionalText = Field(default=None, max_length=1000)
    reject_reason: OptionalText = Field(default=None, max_length=500)


class AftersaleOut(BaseModel):
    """售后单列表项（type/status 的中文由数据字典决定）。"""

    id: int
    no: str
    order_id: int | None = None
    customer_id: int | None = None
    type: str
    type_label: str | None = None
    type_other: str | None = None
    description: str
    status: str
    status_label: str | None = None
    reject_reason: str | None = None
    result: str | None = None
    closed_at: str | None = None
    created_at: str
    updated_at: str
    order_no: str | None = None
    customer_name: str | None = None
    related_aftersale_id: int | None = None
    related_aftersale_no: str | None = None
    related_aftersale_status: str | None = None

    @model_validator(mode="after")
    def _fill_labels(self) -> "AftersaleOut":
        if self.type_label is None:
            self.type_label = labels.aftersale_type(self.type)
        if self.status_label is None:
            self.status_label = labels.aftersale_status(self.status)
        return self


class AftersaleStatusLogOut(BaseModel):
    """售后状态日志。"""

    id: int
    from_status: str | None = None
    to_status: str
    note: str | None = None
    created_at: str


class AftersaleDetailOut(AftersaleOut):
    #: 售后履历（跟进 + 状态变更），PLANNER-V3 §5.8
    timeline: list[dict] = Field(default_factory=list)
    #: 资料汇总（该售后单的跟进附件）
    materials: list[dict] = Field(default_factory=list)
    """售后单详情。"""

    order_id: int
    status_logs: list[AftersaleStatusLogOut] = Field(default_factory=list)


class AftersaleListOut(BaseModel):
    """售后单分页列表。"""

    items: list[AftersaleOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20


class OrderTransitionIn(BaseModel):
    """订单状态转换输入。"""

    to_status: str = Field(min_length=1, max_length=32)
    deposit: float | None = Field(default=None, ge=0)
    balance: float | None = Field(default=None, ge=0)
    payment_screenshots: list[int] | None = Field(default=None)
    logistics_mode: str | None = Field(default=None, max_length=16)
    carrier_id: int | None = Field(default=None, gt=0)
    carrier_contact_id: int | None = Field(default=None, gt=0)
    logistics_fee: float | None = Field(default=None, ge=0)
    tracking_number: str | None = Field(default=None, max_length=64)
    received_at: str | None = None
    note: str | None = Field(default=None, max_length=500)


class OrderTransitionOut(BaseModel):
    """订单状态转换输出。"""

    order: OrderOut
    status_log: OrderStatusLogOut
