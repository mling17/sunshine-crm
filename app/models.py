"""Pydantic 入参/出参模型 + 业务枚举常量。

所有枚举统一从 app/enums.py 导入，确保一致性。
"""

from __future__ import annotations

from typing import Annotated, Optional, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator

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
    note: OptionalText = Field(default=None, max_length=500)
    customer_type: CUSTOMER_TYPE = Field(default="personal")
    source: OptionalText = Field(default=None, max_length=32)
    source_other: OptionalText = Field(default=None, max_length=100)
    intent_level: INTENT_LEVEL | None = None
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
    intent_level: INTENT_LEVEL | None = None
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
    company_name: str | None = None
    owner: str | None = None
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
    lost_reason: str | None = None
    lost_reason_other: str | None = None
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

    @model_validator(mode="after")
    def _fill_stage_label(self) -> "DealOut":
        if self.stage_label is None:
            self.stage_label = labels.deal_stage(self.stage)
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


# ---------------- 跟进 ----------------


class FollowUpOut(BaseModel):
    id: int
    customer_id: int | None = None
    deal_id: int | None = None
    object_type: str | None = None
    object_id: int | None = None
    method: str | None = None
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
    orders: list[dict] = Field(default_factory=list)
    aftersales: list[dict] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


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
    #: 手动/电动 —— 必填由路由层给业务错误码（drive_type_required），不在 pydantic 层拦
    drive_type: OptionalText = Field(default=None, max_length=32)
    note: OptionalText = Field(default=None, max_length=500)


class DealUpdate(BaseModel):
    """改商机：只改传来的字段。``amount``/``stage`` 显式传 null 会在路由层被 400 拒绝。"""

    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: OptionalText = Field(default=None, max_length=200)
    amount: float | None = Field(default=None, ge=0)
    deposit: float | None = Field(default=None, ge=0)
    balance: float | None = Field(default=None, ge=0)
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


# ---------------- 线索 ----------------


class LeadIn(BaseModel):
    """新建线索。"""

    name: Optional[CleanName] = Field(default=None, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    lead_type: CUSTOMER_TYPE = Field(default="personal")
    company_name: OptionalText = Field(default=None, max_length=100)
    source: SOURCE
    source_other: OptionalText = Field(default=None, max_length=100)
    location: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)
    intent_level: INTENT_LEVEL | None = None
    owner: OptionalText = Field(default=None, max_length=32)
    tags: list[TagName] = Field(default_factory=list, max_length=MAX_TAGS)


class LeadUpdate(BaseModel):
    """改线索：只改传来的字段（其余保持原值）。"""

    name: Optional[CleanName] = Field(default=None, max_length=64)
    phone: OptionalText = Field(default=None, max_length=32)
    wechat: OptionalText = Field(default=None, max_length=64)
    lead_type: CUSTOMER_TYPE | None = None
    company_name: OptionalText = Field(default=None, max_length=100)
    source: SOURCE | None = None
    source_other: OptionalText = Field(default=None, max_length=100)
    location: OptionalText = Field(default=None, max_length=200)
    note: OptionalText = Field(default=None, max_length=500)
    intent_level: INTENT_LEVEL | None = None
    owner: OptionalText = Field(default=None, max_length=32)
    # None = 不改标签；[] = 清空标签
    tags: Optional[list[TagName]] = Field(default=None, max_length=MAX_TAGS)


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
    tags: list[str] = Field(default_factory=list)
    duplicate_hint: dict | None = None
    created_at: str
    updated_at: str
    # 派生态（PLANNER-V3 §5.3）：最近一条真实跟进
    last_follow_at: str | None = None
    next_date: str | None = None
    days_overdue: int = 0
    intent_level_label: str | None = None


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
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: OptionalText = Field(default=None, max_length=200)
    amount: float = Field(gt=0)
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
    spec: OptionalText = Field(default=None, max_length=200)
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
    """更新订单。"""

    customer_id: Optional[int] = Field(default=None, gt=0)
    deal_id: Optional[int] = Field(default=None, gt=0)
    product_type: OptionalText = Field(default=None, max_length=32)
    model: OptionalText = Field(default=None, max_length=64)
    spec: OptionalText = Field(default=None, max_length=200)
    amount: Optional[float] = Field(default=None, ge=0)
    owner: OptionalText = Field(default=None, max_length=32)
    # 新增字段
    paid_amount: Optional[float] = Field(default=None, ge=0)
    carrier_id: Optional[int] = Field(default=None, gt=0)
    tracking_number: OptionalText = Field(default=None, max_length=64)


class OrderOut(BaseModel):
    """订单列表项。"""

    id: int
    order_no: str
    customer_id: int
    deal_id: int
    product_type: str | None = None
    model: str | None = None
    spec: str | None = None
    amount: float = 0.0
    status: str
    status_label: str | None = None
    owner: str | None = None
    paid_amount: float = 0.0
    carrier_id: int | None = None
    tracking_number: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="before")
    @classmethod
    def _compat_cols(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            data.setdefault("paid_amount", (data.get("deposit_paid") or 0.0) + (data.get("balance_paid") or 0.0))
            if data.get("tracking_number") is None and data.get("tracking_no") is not None:
                data["tracking_number"] = data.get("tracking_no")
        return data

    @model_validator(mode="after")
    def _fill_status_label(self) -> "OrderOut":
        if self.status_label is None:
            self.status_label = labels.order_status(self.status)
        return self


class OrderDetailOut(BaseModel):
    """订单详情。"""

    id: int
    order_no: str
    customer_id: int
    deal_id: int
    product_type: str | None = None
    model: str | None = None
    spec: str | None = None
    amount: float = 0.0
    status: str
    status_label: str | None = None
    owner: str | None = None
    paid_amount: float = 0.0
    carrier_id: int | None = None
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
    address_id: int | None = None
    receiver_name: str | None = None
    receiver_phone: str | None = None
    receiver_address: str | None = None
    tracking_no: str | None = None
    carrier_contacts: list[dict] = Field(default_factory=list)
    aftersales: list[dict] = Field(default_factory=list)
    deal: dict | None = None
    timeline: list[dict] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _compat_cols(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            data.setdefault("paid_amount", (data.get("deposit_paid") or 0.0) + (data.get("balance_paid") or 0.0))
            if data.get("tracking_number") is None and data.get("tracking_no") is not None:
                data["tracking_number"] = data.get("tracking_no")
        return data

    @model_validator(mode="after")
    def _fill_status_label(self) -> "OrderDetailOut":
        if self.status_label is None:
            self.status_label = labels.order_status(self.status)
        return self


class OrderStatusLogOut(BaseModel):
    """订单状态日志。"""

    id: int
    order_id: int
    from_status: str | None = None
    to_status: str
    note: str | None = None
    created_at: str


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
    tracking_number: str | None = Field(default=None, max_length=64)
    received_at: str | None = None
    note: str | None = Field(default=None, max_length=500)


class OrderTransitionOut(BaseModel):
    """订单状态转换输出。"""

    order: OrderOut
    status_log: OrderStatusLogOut
