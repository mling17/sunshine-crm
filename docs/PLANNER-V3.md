# CRM V2 定稿技术方案（V3）

> 版本：v3.0 · 2026-10-31 ｜ 状态：**待开工**（用户已定稿前端，后端按本文改造）
>
> 上游权威输入（本文不改其一字）：
> - 页面规格：`docs/PAGES-V2.md` §7–§14 —— v2.1–v2.7 共 7 批用户逐条定稿，2026-10-31 冻结
> - 业务架构：`docs/BUSINESS-ARCH-V2.md` —— 8 项核心业务决议
> - 代码基线：`static/demo/**` —— 纯 Mock 前端，git tag **`frontend-final-v2.7`** @ `69db12d`
>
> **本文替代 `PLANNER-V2.md`**。那份写于 v2.1 定稿之前，「8 阶段」「图片最多 3 张」「物流方式 carrier|self」「确认即赢单」等口径均已作废；
> 其迁移脚本（`docs/planner-v2-migrations_v2.py`）与回归基线（182 条）仍有效，保留参考价值。
> 冲突时的判据顺序：**PAGES-V2.md（用户原话）> 本文 > PLANNER-V2.md**。
>
> 交付对象：@coder（§10 任务卡）、@reviewer（§9 断言表）、@ops（§7 发布与回滚）

---

## 0. 方案总览

### 0.1 一句话技术路线

**前端已冻结，后端补齐契约**：在现有 V2 后端上做**一次增量迁移（`v2_002`）+ 契约改造**，把枚举/字段/接口对齐定稿页面；
正式前端以 demo 的 `views/*.js` 为基线接管（需把 93 处 `window.DEMO` 直读改成接口调用，§8.2），不再另写一套页面。

### 0.2 为什么是改造而不是重写

| # | 事实 | 结论 |
|---|---|---|
| 1 | 现有 19 张表 / 41 索引 / 182 条 unittest 全绿，登录、会话、上传、导入、systemd 部署、每日备份均已跑通 | 基础设施不动 |
| 2 | 业务表当前**全部 0 行**（`customers`/`deals`/`orders`/`follow_ups`… 皆空，仅 `users` 1 行） | 迁移无需复杂存量映射，风险大幅下降 |
| 3 | 定稿的增量集中在「枚举语义 + 3 张新表 + 21 个新列 + 字典/统计两个新面」 | 加表加列级别，不是重画数据模型 |
| 4 | 云主机 15G 内存仅剩 791M，禁止加容器与中间件 | 单进程 uvicorn + SQLite 不变 |

### 0.3 三条硬边界（评审别再翻）

1. **金额遮罩是纯前端**：`state.showMoney` 默认 `false`（显示 `¥••••`），API 照常返回真实金额，后端不做脱敏、不加权限。
2. **字典分级由代码注册表强制**：谁能新增/删除写在 `app/dicts.py::DICT_REGISTRY`（A/B/C/D），选项值存库；B/C/D 类**不提供新增/删除接口**，越权请求直接 403。
3. **附件放开到任意类型后必须防内联执行**：下载响应一律 `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`，`.html/.svg/.js` 不得被浏览器当页面执行。

### 0.4 交付物清单

| # | 文件 | 动作 |
|---|---|---|
| 1 | `app/enums.py` | 改枚举值域 + 新增 `DRIVE_TYPE`/`TIMELINE_TYPE` |
| 2 | `app/dicts.py` | **新增**字典注册表 + 读写校验 |
| 3 | `app/migrations.py` | 追加 `v2_002` 迁移（§7.2） |
| 4 | `app/routers/dicts.py`、`stats.py` | **新增**两个 router |
| 5 | `app/routers/{deals,orders,customers,carriers,followups,aftersales,dashboard,leads}.py` | 按 §5 改契约 |
| 6 | `app/storage.py`、`app/services.py` | 附件白名单/上限、订单号、履历写入抽公共函数 |
| 7 | `static/views/*.js` | 以 `static/demo/views/*.js` 为基线覆盖，并把 93 处 `window.DEMO` 直读改成接口调用（§8.2） |
| 8 | `tests/test_{dicts,deal_orders,order_timeline,addresses_contacts,files,stats_workbench}.py` | 按 §9.3 新增 6 个测试文件（96 条） |

---

## 1. 定稿基线（coder 的唯一字段来源，照抄，不要自己推）

### 1.1 枚举权威表

| 枚举 | 值 | 中文 | 落库位置 | 相对现有 V2 的差异 |
|---|---|---|---|---|
| `CUSTOMER_TYPE` | `personal` / `company` | 个人 / 公司 | `customers.customer_type`、`leads.lead_type` | 不变 |
| `LEAD_STATUS` | `new` / `following` / `converted` / `invalid` | 新线索 / 跟进中 / 已转化 / 已失效 | `leads.status` | 不变 |
| `SOURCE` | `wechat`/`phone`/`referral`/`existing`/`stock`/`other` | 微信/电话/转介绍/老客户/存量/其他 | `leads.source`、`customers.source` | 不变 |
| `INTENT_LEVEL` | `high`/`medium`/`low`/`none` | 高/中/低/无意向 | `leads`/`customers.intent_level` | **新建默认 `medium`**（原无默认） |
| `DEAL_STAGE` | `quote` / `confirm` / `won` / `lost` | **报价** / **待客户确认** / **成交** / **流失** | `deals.stage` | ⚠️ `quote` 排第一位；`confirm` 复用旧 key 但**中文从「需求确认」改为「待客户确认」**；`negotiate` **删除** |
| `DRIVE_TYPE` | `manual` / `electric` | 手动 / 电动 | `deals.drive_type` | **新增**，商机必填 |
| `DEAL_LOST_REASON` | `price`/`competitor`/`give_up`/`budget`/`other` | 价格/竞品/客户放弃/预算不足/其他 | `deals.lost_reason` | 不变 |
| `ORDER_STATUS` | `pending_payment`/`deposit_paid`/`producing`/`balance_paid`/`ready_to_ship`/`shipped`/`completed` | 待支付/已付押金/生产中/已付尾款/待发货/已发货/已完成 | `orders.status` | 不变（7 态机不变） |
| `LOGISTICS_MODE` | `free` / `agent` / `self` | **包邮** / **代办** / **自提** | `orders.logistics_mode` | ⚠️ 值域由 `carrier/self` 改为 `free/agent/self` |
| `AFTERSALE_TYPE` | `return`/`exchange`/`repair`/`complaint`/`other` | 退货/换货/维修/投诉/其他 | `aftersales.type` | 不变 |
| `AFTERSALE_STATUS` | `pending` / `processing` / `done` | 待处理 / 处理中 / 已完成 | `aftersales.status` | ⚠️ `rejected` **停用**（列与历史值保留，可读不可写） |
| `FOLLOW_OBJECT` | `lead`/`customer`/`deal`/`order`/`aftersale` | 线索/客户/商机/订单/售后 | `follow_ups.object_type` | 不变 |
| `FOLLOW_METHOD` | `wechat` / `phone` | 微信 / 电话 | `follow_ups.method` | ⚠️ `visit`/`online` **删除**，默认 `wechat` |
| `TIMELINE_TYPE` | `follow`/`create`/`change`/`stage`/`order`/`aftersale`/`pay`/`ship`/`address` | 跟进/创建/编辑/状态变更/生成订单/售后/收款/发货/修改收货 | 商机等：`follow_ups.kind`；订单：`order_status_log.event_type` | **新增**。两处**同值域**，前端一套 `RECORD_META` 渲染；出参统一字段名 `type`+`type_label`（`edit` 一律用 `change`，照 demo） |
| `PRODUCT_MODEL` | 30 个型号 key（`XW-120`…`YG-50`） | 型号显示名 | `deals.model`、`orders.model` | **新增**，走字典 A 类，`meta` 带 `product`/`size`/`drive` |
| `PRODUCT_TYPE` | `天窗`/`天幕`/`阳光房`/`遮阳帘` | — | `deals.product_type`、`orders.product_type` | 由自由文本改为字典 A 类下拉（Q8 方案乙） |

> **存储值永远是英文小写蛇形**；中文只出现在 `*_LABELS` 与出参 `*_label`。字典改名后历史数据中文跟着变 —— 数据里存 key，不存中文。

### 1.2 对象字段基线

**leads（线索）**：`name`·`phone`·`wechat`·`lead_type`·`company_name`·`location`·`source`·`source_other`·`intent_level`(默认 medium)·`tags[]`·`status`·`invalid_reason`·`note`·`created_at`；列表另出派生字段 `last_follow_at`（最近一条跟进的 created_at）与 `next_date`（最近一条跟进的 next_date）。

**customers（客户）**：现有 14 列 + **画像 7 项** `house_type`（房屋类型）·`floor`（楼层）·`install_at`（安装位置）·`decoration_stage`（装修阶段）·`budget`（预算）·`decider`（决策人）·`concerns`（关注点，JSON 数组）+ **地址簿** `addresses[]`。客户**只能由线索转化产生**，前端不提供新增入口（API 保留兼容 V1）。

**deals（商机）**：`customer_id`·`product_type`（字典）·`model`（型号 key，可搜索下拉）·`spec`（尺寸，选中型号自动带出、可手改）·`drive_type`（手动/电动，必填）·`amount`·`stage`（默认 `quote`）·`note`·`order_id`·`locked`（派生：`order_id` 非空即锁）·`created_at`·`updated_at`。
**不再有定金/尾款字段参与录入**（v2.3 定稿删除），`deals.deposit/balance` 列保留只为 V1 兼容。

**orders（订单）**：`order_no`·`customer_id`·`deal_id`·`product_type`·`model`·`spec`·`amount`·**`deposit_amount`（计划押金）**·**`balance_amount`（计划尾款 = 总额 − 押金）**·`deposit_paid`·`balance_paid`·`logistics_mode`·`carrier_id`·**`logistics_fee`**·`tracking_number`·**`address_id`**·**`receiver_name`/`receiver_phone`/`receiver_address`（下单时快照）**·`status`·`note`·`timeline[]`。

**aftersales（售后）**：`no`·`order_id`·`customer_id`·`type`·`description`·`status`（`pending`→记跟进自动 `processing`→`done`）·`result`·`closed_at`；**无「新建」入口**（只能从订单生成，且订单必须 `completed`）；**无「拒绝」操作**；`done` 后禁止再加跟进。

**carriers（物流公司）**：`name`·`note`·`is_active`·**`contacts[]`（多联系人：`name`/`phone`/`tags[]`，v2.3 去掉「职务」改标签）**·`order_count`（被订单关联次数，派生）。被引用 >0 **只能停用不能删除**。

**follow_ups（统一跟进/履历）**：`object_type`·`object_id`·`kind`·`method`·`content`·`next_date`（可为空 = 本次不需要跟进）·`files[]`（任意类型，≤10 个/条，单个 ≤20MB）·`created_at`。
**next_date 口径**：同一对象以**最近一条 `kind='follow'`** 的 next_date 为准（一天记多次只认最后一次）。

**attachments（附件）**：`file_name`·`mime_type`·`size`·`storage_key`·`object_type`（`follow_up`/`order_payment`/`aftersale`）·`is_image`（派生，决定前端出缩略图还是文件条）。

### 1.3 数据字典（12 张，分级 × 维护能力）

| code | 名称 | 级别 | 可做什么 | 选项数（定稿） |
|---|---|---|---|---|
| `product_model` | 产品型号 | **A** | 增/改/排序/停用 | 30 |
| `customer_source` | 客户来源 | A | 增/改/排序/停用 | 6 |
| `intent_level` | 意向等级 | A | 同上 | 4 |
| `product_type` | 产品类型 | A | 同上 | 4 |
| `lost_reason` | 商机流失原因 | A | 同上 | 5 |
| `aftersale_type` | 售后类型 | A | 同上 | 5 |
| `follow_method` | 跟进方式 | A | 同上（定稿只有微信/电话） | 2 |
| `deal_stage` | 商机阶段 | **B** | 仅改名 + 排序，**不能增删** | 4 |
| `order_status` | 订单状态 | B | 仅改名 + 排序 | 7 |
| `aftersale_status` | 售后状态 | B | 仅改名 + 排序 | 3 |
| `customer_type` | 客户类型 | **C** | 仅改名（背后绑「公司名是否必填」） | 2 |
| `follow_object` | 跟进对象类型 | **D** | 只读展示 | 5 |

**统一规则**：被引用 >0 的选项**禁止删除**，只能停用；停用后不出现在新建/编辑下拉，但列表与详情照常显示中文名；改显示名后历史数据文案立即跟着变。

### 1.4 页面 → 端点映射（13 个页面）

| 页面 | 路由 | 主要端点 |
|---|---|---|
| 工作台 | `#/dashboard` | `GET /dashboard`（§5.2 出参改造） |
| 线索列表 | `#/leads` | `GET /leads`、`POST /leads`、`PUT /leads/{id}`、`POST /leads/{id}/convert` |
| 线索跟进页 | `#/leads/{id}/follow` | `GET /follow-ups?object_type=lead&object_id=`、`POST /follow-ups` |
| 客户列表 | `#/customers` | `GET /customers`、`PUT /customers/{id}` |
| 客户详情（画像） | `#/customers/{id}` | `GET /customers/{id}/360`、`GET/POST/PUT/DELETE /customers/{id}/addresses` |
| 客户跟进 | `#/customers/{id}/follow` | 同线索跟进页 |
| 商机列表 | `#/deals` | `GET /deals`、`POST /deals`、`PUT /deals/{id}` |
| 商机跟进页 | `#/deals/{id}` | `GET /deals/{id}`（含 timeline + materials）、`POST /deals/{id}/orders` |
| 订单列表 / 详情 | `#/orders`、`#/orders/{id}` | `GET /orders`、`GET /orders/{id}`、`POST /orders/{id}/pay-deposit|pay-balance`、`POST /orders/{id}/transition` |
| 售后 | `#/aftersales` | `GET /aftersales`、`GET /aftersales/{id}`、`POST /aftersales/{id}/finish`、`POST /aftersales`（仅订单页调用） |
| 物流 | `#/logistics` | `GET/POST/PUT/DELETE /carriers`（内嵌 `contacts[]`） |
| 统计 | `#/stats` | `GET /stats`（**新增**） |
| 数据字典 | `#/dict`、`#/dict/{code}` | `GET /dicts`、`GET /dicts/{code}`、`POST/PUT/DELETE /dicts/{code}/items`（**新增**） |

---

## 2. 现状与差距（G 清单）

> 现状均引自代码实测（行号对应 `69db12d`）。每条都给出「改造动作」与「主要影响文件」，逐条销项。

### 2.1 阻塞级（不改就跑不通定稿页面）

| # | 定稿要求 | 现状 | 改造动作 |
|---|---|---|---|
| **G-01** | 商机阶段 = 报价 → 待客户确认 → 成交/流失 | `app/enums.py:64` `DEAL_STAGE = confirm/quote/negotiate/won/lost`，中文「需求确认」 | 改为 4 值；`negotiate` 删除；`confirm` 中文改「待客户确认」；`quote` 排首位、新建默认 `quote`；同步 `STAGE_LABELS`/`STAGES`（models.py）与前端 `app.js` |
| **G-02** | 商机必填「手动/电动」+ 备注 | `deals` 表无 `drive_type`、无 `note` | 加 2 列（§3.2 D-1） |
| **G-03** | 「生成订单」需填押金/物流方式/承运/运费/收货地址/运单号/备注 | `app/routers/deals.py:188` `POST /deals/{id}/win` **无入参**，只继承商机金额（`:222` INSERT 只写 8 列） | 新增 `POST /deals/{id}/orders`（带 payload）；旧 `/win` 保留为无参兼容（内部转调） |
| **G-04** | 只有「成交」阶段才允许生成订单 | `/win` 只挡 `won/lost`（冻结），`quote` 阶段也能生成 | 前置断言 `stage='won'`，否则 409 `deal_not_won`「先把阶段推进到成交」 |
| **G-05** | 订单号形如 `SO-20261031-001` | `app/services.py:49 next_no(... now_local_iso()[:8])` 传入带横线的 `2026-10-31`，生成 `SO-2026-10--001` | `next_no` 内部把日期规整为 `YYYYMMDD`（`re.sub(r'\D','',day)`） |
| **G-06** | 物流方式 = 包邮 / 代办 / 自提 | `app/enums.py:102` `LOGISTICS_MODE = carrier/self` | 改 `free/agent/self`；迁移把 `carrier→agent`、`self→self` |
| **G-07** | 订单要存运费、收货人、地址簿关联 | `orders` 只有 `carrier_id/tracking_no`，无收货字段 | 加 5 列（§3.3） |
| **G-08** | 订单详情要「押金/尾款」计划值（收款五个数字） | 只有 `deposit_paid/balance_paid`（已收），无计划押金 | 加 `deposit_amount`/`balance_amount`，生成订单时由押金算出尾款 |
| **G-09** | 跟进可传**任意类型**附件，≤10 个/条、单个 ≤20MB | `app/services.py:62 read_images` 只收图片，`:94` 硬限 **3 张**；`app/storage.py:50` 20MB | 新 `read_files`（白名单 pdf/xls/xlsx/doc/docx/dwg/dxf/zip/图片 + MIME 嗅探）；上限 10；`MAX_PHOTOS=3` 全量改 10 |
| **G-10** | 商机履历含「创建/编辑/阶段变更/生成订单」，订单履历含 6 类事件 | `follow_ups` 只存真实跟进；`order_status_log` 只有 from/to/金额/截图 | `follow_ups` 加 `kind`+`detail`；`order_status_log` 加 `event_type`+`detail`（§3.5） |
| **G-11** | 工作台待跟进 = 按客户取**最近一条**跟进的 next_date 判断 | `app/routers/dashboard.py:35` SQL 是「所有历史记录 next_date ≤ 今天」，旧记录永不消失 | 改成窗口函数取每客户最新 `kind='follow'` 一条（§6.1） |
| **G-12** | 数据字典 12 张可维护 | 无字典表、无接口；`enums.py` 里 `Literal` 硬校验，前端 `app.js` 又硬编码一份 | 新增 `dict_items` 表 + `app/dicts.py` 注册表 + `app/routers/dicts.py`（§3.6、§4） |
| **G-13** | 产品型号可搜索下拉（30 个，选中带出尺寸） | `deals.model` 自由文本 | 型号走字典 `product_model`（`meta` 带 size/product）；`GET /dicts/product_model?q=` 支持按 key/尺寸模糊过滤 |

### 2.2 功能级（页面能开，但功能缺）

| # | 定稿要求 | 现状 | 改造动作 |
|---|---|---|---|
| **G-14** | 客户画像 7 项 | `customers` 无画像列 | 加 7 列（§3.1 C-1）；`GET /customers/{id}/360` 出参带 `profile` |
| **G-15** | 客户地址簿（下单可从历史地址选、新增存回） | 无 | 新表 `customer_addresses`（§3.1 C-2）+ 4 个端点 |
| **G-16** | 物流公司多联系人 + 标签 | `carriers` 单 `contact_person/phone` | 新表 `carrier_contacts`（§3.4）+ `carriers` 出参内嵌 `contacts[]`（保留旧列兼容 V1） |
| **G-17** | 统计页 8 块图（KPI/趋势/漏斗/线索转化/阶段分布/订单状态/客户来源/售后类型） | **无 `/stats` 端点**；`static/views/stats.js` 只有 2KB 占位 | 新增 `app/routers/stats.py`（§5.9） |
| **G-18** | 售后：记跟进自动 `processing`、无「开始处理」、无「拒绝」、`done` 后禁跟进 | `aftersales` 有 `/start`、`/reject`；状态不随跟进变化 | 删 `/start`、`/reject`（或返回 410 并给提示）；跟进创建路径里对 `aftersale` 对象自动置 `processing`；`done` 时 `POST /follow-ups` 返回 409 `aftersale_closed` |
| **G-19** | 线索列表显示「上次跟进时间/逾期天数」 | `leads` 列表 SQL 不 join 跟进 | 子查询取最近一条 `kind='follow'` 的 `created_at`/`next_date`，出参加 `last_follow_at`/`days_overdue` |
| **G-20** | 商机详情不显示「商机名称：未命名」 | 前端 `static/views/deals.js` 硬显示不存在的 `title`（`deals.title` 列存在但从未写入） | 前端删该字段；后端 `DealOut` 不再返回 `title`（列保留） |

### 2.3 前端接管（必须和 G 清单同批做，否则后端白改）

| # | 定稿要求 | 现状 | 改造动作 |
|---|---|---|---|
| **G-21** | 正式前端 = demo 定稿版 | `static/views/*.js` 仍是旧 V2（8 阶段、图片 3 张、carrier/self），与 demo 两套并存；且 demo 视图有 **93 处直读 `window.DEMO`**、写操作是 `mockWrite` 假成功，**不是现成的接口客户端** | ① 以 demo 视图为基线覆盖 `static/views/`；② 逐视图把 93 处直读改成 `api()` 调用（§8.2 按视图列表）；③ 把假成功改成真实写接口；④ `app.js` 的 `api()` 换真实 fetch + 枚举走字典；⑤ `sw.js` 版本号 +1 |
| **G-22** | 客户页无「新增客户」 | `static/views/customers.js` 有新增按钮 | 移除按钮，保留说明文案「客户由线索转化，不在此新建」；`POST /customers` API 保留（V1 兼容，前端不调用） |

### 2.4 差距销项口径

- 每条 G 必须落到一个测试用例或一条断言（§9 表里 `用例` 列反查 G 号）；
- G-01/G-06/G-09 是**破坏性变更**（改枚举值域、改上限），必须在同一次发布里前后端一起切，禁止只发一半；
- G-05/G-07/G-08 只影响新建订单，历史订单 0 条，无需回填。---

## 3. 数据模型改造（迁移 `v2_002`）

> 全部 `ALTER TABLE ... ADD COLUMN` 与 `CREATE TABLE IF NOT EXISTS`，**不重建、不删列、不改类型**。
> 现状 19 张表（17 业务 + `schema_migrations` + `migration_clear_guard`）→ 迁移后 **22 张**（新增 3 张），索引 41 → **50**（新增 9 个）。

### 3.1 客户（G-14 / G-15）

```sql
-- C-1 客户画像（7 列，1:1 挂在 customers 上，单用户单库不值得单开表）
ALTER TABLE customers ADD COLUMN house_type       TEXT;  -- 房屋类型：高层公寓/别墅/自建房/工地工程…
ALTER TABLE customers ADD COLUMN floor            TEXT;  -- 楼层：18/32 顶楼
ALTER TABLE customers ADD COLUMN install_at       TEXT;  -- 安装位置：主卧/客厅/阳台/阳光房
ALTER TABLE customers ADD COLUMN decoration_stage TEXT;  -- 装修阶段：未开工/水电/泥木/安装中
ALTER TABLE customers ADD COLUMN budget           TEXT;  -- 预算：1–1.5 万（业务习惯用区间，存文本）
ALTER TABLE customers ADD COLUMN decider          TEXT;  -- 决策人
ALTER TABLE customers ADD COLUMN care             TEXT;  -- 关注点：JSON 数组字符串 ["防水","颜值"]

-- C-2 客户地址簿（下单可选历史地址，新增自动回存）
CREATE TABLE IF NOT EXISTS customer_addresses (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  label         TEXT,            -- 家 / 工地 / 库房
  receiver_name TEXT NOT NULL,
  phone         TEXT NOT NULL,
  address       TEXT NOT NULL,
  is_default    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_addr_customer ON customer_addresses(customer_id);
```

**API 出参映射（务必照此，前端 demo 已按这套 key 写好）**：`profile = {house_type, floor, install_at, stage(←decoration_stage), budget, decider, care[]}`；`addresses = [{id,label,receiver_name,phone,address,is_default}]`。

### 3.2 商机（G-01 / G-02 / G-13）

```sql
ALTER TABLE deals ADD COLUMN drive_type TEXT;                -- manual | electric，新建必填
ALTER TABLE deals ADD COLUMN note       TEXT;                -- 备注（v2.3 定稿）
ALTER TABLE deals ADD COLUMN locked_at  TEXT;                -- 生成订单时写；NULL=未锁（锁定另可派生 order_id 非空）
CREATE INDEX IF NOT EXISTS idx_deals_stage  ON deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_cust   ON deals(customer_id);
```

**阶段数据迁移**（当前 0 行，仍写全，防其它环境有数据）：

```sql
UPDATE deals SET stage='quote'   WHERE stage IN ('confirm','quote');
UPDATE deals SET stage='confirm' WHERE stage='negotiate';
UPDATE deals SET stage='won'     WHERE stage='won';
UPDATE deals SET stage='lost'    WHERE stage='lost';
-- 旧 V1 阶段（若从 V1 库直接升）
UPDATE deals SET stage='quote'   WHERE stage IN ('lead','quoted');
UPDATE deals SET stage='confirm' WHERE stage IN ('confirmed','deposit','producing','balance','shipped');
```

> ⚠️ **`confirm` 这个 key 语义变了**：旧 = 需求确认（漏斗第一段），新 = 待客户确认（漏斗第二段）。因为业务表 0 行、且旧 `confirm` 与旧 `negotiate` 在新模型里都该落到「待客户确认」，上面的双 UPDATE 必须在同一个事务里顺序执行，**不能先 `negotiate→confirm` 再 `confirm→quote`**。

### 3.3 订单（G-05 / G-06 / G-07 / G-08）

```sql
ALTER TABLE orders ADD COLUMN deposit_amount      REAL;   -- 计划押金（下单时填）
ALTER TABLE orders ADD COLUMN balance_amount      REAL;   -- 计划尾款 = amount - deposit_amount
ALTER TABLE orders ADD COLUMN logistics_fee       REAL NOT NULL DEFAULT 0;  -- 运费（包邮=0，自提=0）
ALTER TABLE orders ADD COLUMN address_id          INTEGER REFERENCES customer_addresses(id) ON DELETE SET NULL;
ALTER TABLE orders ADD COLUMN receiver_name       TEXT;   -- 下单快照（地址簿后续被改不影响历史单）
ALTER TABLE orders ADD COLUMN receiver_phone      TEXT;
ALTER TABLE orders ADD COLUMN receiver_address    TEXT;
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_cust   ON orders(customer_id);
```

**物流方式迁移**：`UPDATE orders SET logistics_mode='agent' WHERE logistics_mode='carrier';`（`self` 语义仍是自提，保留）。

> 收款口径：`deposit_paid`/`balance_paid` 仍是「已收」，`deposit_amount`/`balance_amount` 是「应收」。
> **恒等式（Q-D）**：`amount = deposit_amount + balance_amount`，由服务端强制，写库前 `round(x,2)` 后比对，不允许差 1 分钱。
> 订单详情「收款五个数字」= `amount`(总额) / `deposit_amount`(押金) / `balance_amount`(尾款) / `deposit_paid+balance_paid`(已收) / `amount - 已收`(未收)。

### 3.4 物流公司多联系人（G-16）

```sql
CREATE TABLE IF NOT EXISTS carrier_contacts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  phone      TEXT NOT NULL,
  tags       TEXT,            -- JSON 数组 ["大件业务","报价"]（v2.3 去掉「职务」改标签）
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_carrier_contacts ON carrier_contacts(carrier_id);
```

**兼容**：`carriers.contact_person/phone` 两列保留不删，作为「主联系人」同步写入第 1 条 `carrier_contacts`（V1 出参只增不改）；`DELETE /carriers/{id}` 已有「被订单引用 → 409」守卫，迁移不动。

### 3.5 履历（G-10）

```sql
-- 统一跟进表扩为「对象履历」：真实跟进 kind='follow'，其它是系统自动写入
ALTER TABLE follow_ups ADD COLUMN kind   TEXT NOT NULL DEFAULT 'follow';  -- follow|create|change|stage|order|aftersale|pay|ship|address
ALTER TABLE follow_ups ADD COLUMN detail TEXT;                            -- JSON：字段变化明细/订单摘要
CREATE INDEX IF NOT EXISTS idx_fu_obj  ON follow_ups(object_type, object_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fu_kind ON follow_ups(kind);

-- 订单履历：从「状态日志」升级为「事件流」
ALTER TABLE order_status_log ADD COLUMN event_type TEXT NOT NULL DEFAULT 'stage';
-- 与 follow_ups.kind 同值域：order|pay|stage|ship|address|aftersale
ALTER TABLE order_status_log ADD COLUMN detail TEXT;   -- JSON：金额/运单号/收货信息/售后单号
```

**写入规则（写进 `app/services.py`，router 不许自己拼 SQL）**：

| 触发 | 写哪 | kind / event_type | content 样例 |
|---|---|---|---|
| 新建线索/客户/商机 | `follow_ups` | `create` | 创建商机：天窗 XW-120 1200×2400，报价 ¥12,000 |
| 编辑商机（有字段变化） | `follow_ups` | `change` | 尺寸由 1200×2200 改为 1200×2400（现场复尺）；`detail` 存 `{field:{from,to}}` |
| 改阶段 | `follow_ups` | `stage` | 阶段推进：待客户确认 → 成交 |
| 生成订单 | `follow_ups` + `order_status_log` | `order` / `order` | 生成订单 SO-20261031-001，押金 ¥20,000，物流 代办/德邦 |
| 收押金 / 收尾款 | `order_status_log` | `pay` | 收押金 ¥20,000（2 张截图） |
| 订单状态推进 | `order_status_log` | `stage` | 待支付 → 已付押金 |
| 发货 | `order_status_log` | `ship` | 已发货，运单号 SF7788123400 |
| 改收货地址/运单 | `order_status_log` | `address` | 收货地址改为 …（detail 存前后值） |
| 订单添加售后 | `order_status_log` + `follow_ups`(售后对象) | `aftersale` | 添加售后单 AS-20261031-001 |
| 售后记跟进 | `follow_ups` | `follow` | 原文内容（同时自动置 `processing`） |
| 售后完成 | `follow_ups` + `aftersale_status_log` | `stage` / 状态日志 | 处理中 → 已完成（含结论） |

> **附件**：`attachments` 表结构不动（`mime_type`/`size` 已在），只放开白名单与上限，`is_image` 由 `mime_type.startswith('image/')` 派生，不落库。

### 3.6 数据字典（G-12）

```sql
CREATE TABLE IF NOT EXISTS dict_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  dict_code  TEXT NOT NULL,      -- 字典 code（见 §4.1 注册表）
  key        TEXT NOT NULL,      -- 存储值，保存后不可改
  label      TEXT NOT NULL,      -- 显示名，随时可改
  sort       INTEGER NOT NULL DEFAULT 0,
  enabled    INTEGER NOT NULL DEFAULT 1,
  meta       TEXT,               -- JSON：product_model 存 {"product":"天窗","size":"900×1800","drive":"electric"}
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(dict_code, key)
);
CREATE INDEX IF NOT EXISTS idx_dict_code ON dict_items(dict_code, sort);
```

**种子数据**：11 张系统字典按 `app/enums.py` 现有值灌入；`product_model` 灌定稿的 30 个型号（demo `PRODUCT_MODELS` 原样搬，`used` 字段不落库，实时算）。

### 3.7 索引与体积

- 新增 11 个索引（上列），全部 `IF NOT EXISTS`；
- 单用户数据量级：客户 <10³、跟进 <10⁵，索引足以支撑，不做分页优化以外的动作；
- 迁移后 `PRAGMA integrity_check` 必须 `ok`，`PRAGMA foreign_key_check` 必须空。

---

## 4. 数据字典机制（A/B/C/D 分级怎么落地）

### 4.1 代码注册表（唯一真源 `app/dicts.py`）

```python
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
```

### 4.2 校验双层结构（关键，别退化成单层）

| 层 | 职责 | 举例 |
|---|---|---|
| 代码 `Literal`（`enums.py`） | 保证**状态机可推进**、label 兜底、测试可静态断言 | `ORDER_STATUS` 7 值写死在 `Literal` |
| 数据库 `dict_items` | 保证**显示名/顺序/启用**可改、可新增业务标签 | 加来源「抖音」、把「赢单」改叫「成交」 |

**规则**：

1. **A 类**：写入校验 = `SELECT 1 FROM dict_items WHERE dict_code=? AND key=? AND enabled=1`；新增 key 立即生效，无需发版；
2. **B/C/D 类**：写入校验仍走代码 `Literal`（状态机不许被字典塞出新值）；字典只影响**显示名与顺序**；
3. **改名不复制数据**：业务表只存 key，出参时 `label` 从字典查（带内存缓存，进程内 `lru_cache` + 写操作 `clear()`）；
4. **删除守门**：`used = COUNT(*)` 按注册表 `table` 里的列统计；`used>0` → 409 `dict_item_in_use`「有 N 条数据在用，只能停用」；
5. **停用不改历史**：`enabled=0` 只让下拉不出现，历史数据照常显示中文名。

### 4.3 与前端的关系

- 前端**不再硬编码任何下拉**（`app.js` 里 `STAGES`/`SOURCE_LABELS` 等改成启动时 `GET /dicts` 灌入，`core.js` 保留兜底常量）；
- `deal_stage` 的 key→中文由字典提供：改「赢单」→「成交」是数据操作，不是发版。

---

## 5. API 契约

> 前缀不变：对外 `/crm/api/crm/...` → 后端 `/api/crm/...`（nginx `location /crm/api/` 反代 8010）。
> 认证不变：HttpOnly Session Cookie。
> 错误统一沿用仓库既有格式 `{"detail": "中文提示", "code": "err_code"}`（`app/errors.py` 的 `ApiError`）；**detail 直接给用户看**，中文、可读、不带堆栈。

### 5.1 约定

| 项 | 约定 |
|---|---|
| 列表分页 | `GET ?page=1&size=20`，返回 `{items, total, page, size}`（沿用现有） |
| 时间 | `created_at/updated_at` UTC ISO(`Z`)；业务日期/成交时间本地无时区（沿用 §0.3 旧约定，不改） |
| 金额 | REAL，出参 `round(x,2)`；**不做脱敏** |
| 枚举出参 | 每个枚举字段都带 `<field>_label`，前端不做映射表 |
| 幂等 | 生成订单、收款、完成售后都靠状态前置校验挡重复（409），不做幂等键 |

### 5.2 工作台 `GET /dashboard`（G-11 / G-17）

出参（新增字段标 ★，其余保留）：

```jsonc
{
  "today_followups": [{"id":11,"object_type":"customer","object_id":9,"customer_id":9,"customer_name":"…",
                       "deal_id":8,"deal_stage":"confirm","deal_stage_label":"待客户确认",
                       "content":"…","next_date":"2026-10-31","days_overdue":0}],
  "month_won": {"count": 3, "amount": 46500.0},
  "stats": {
    "customers_total": 10,
    "month_new_customers": 2,
    "repeat_customers": 3,
    "in_progress_deals": {"count": 5, "amount": 128000.0},     // ★ 非 won/lost
    "deals_by_stage": {"quote":2,"confirm":3,"won":7,"lost":1},
    "orders_by_status": {"pending_payment":{"count":1,"amount":8600.0}, "...":{}},
    "recent_activities": [                                      // ★ 混合动态 10 条，时间倒序
      {"at":"2026-10-31T09:12:00","type":"follow","actor":"陈明",
       "text":"张三 · 记了一条跟进","object_type":"customer","object_id":4,"amount":null},
      {"at":"2026-10-30T16:40:00","type":"order","actor":"陈明",
       "text":"李四订单 → 已付押金","object_type":"order","object_id":2,"amount":20000.0}
    ],
    "aftersale_sla_alerts": [{"id":1,"no":"AS-20261031-001","days_pending":4,"order_no":"…","customer_name":"…"}]
  }
}
```

**待跟进 SQL（§6.1）**：按客户取**最近一条 `kind='follow'`** 的 `next_date`，`≤ 今天` 且该客户名下商机未 `won`/`lost` → 入列；`days_overdue = today - next_date`（同日=0）。

### 5.3 线索 `/leads`

| 方法 | 路径 | 变更 |
|---|---|---|
| GET | `/leads` | ★ 出参加 `last_follow_at`、`next_date`、`days_overdue`、`intent_level_label`、`source_label`；`intent_level` 默认 `medium` |
| POST | `/leads` | `intent_level` 缺省填 `medium`；`source` 校验走字典 |
| GET | `/leads/{id}` | 加 `follow_summary{last_follow_at,next_date,count}` |
| PUT | `/leads/{id}` | 不变（字段随 §1.2） |
| POST | `/leads/{id}/invalidate` | 不变 |
| GET | `/leads/convert-check?phone=&wechat=` | 不变（重号提示） |
| POST | `/leads/{id}/convert` | 入参加 `drive_type`、`model`、`spec`、`amount`、`note`；**不再收 deposit/balance**；建客户（画像空）+ 建商机（`stage='quote'`）+ 线索置 `converted`；写 `kind='create'` 履历 |
| POST | `/import/preview`、`/import/commit` | 不变（模板列见 PAGES §7.3） |

### 5.4 客户 `/customers`

| 方法 | 路径 | 变更 |
|---|---|---|
| GET | `/customers` | ★ 出参加 `deals_total`、`deals_won_total`、`deal_amount_total`、`is_repeat`、`last_follow_at`、`profile`（概要）、`addresses` |
| GET | `/customers/{id}/360` | ★ 出参 `profile` + `addresses` + `deals` + `orders` + `aftersales` + `materials`（资料汇总，见 §5.7） |
| POST | `/customers` | **保留但前端不调用**（V1 兼容；若调用，视为手工建档，写 `kind='create'` 履历） |
| PUT | `/customers/{id}` | ★ 支持 `profile{...}` 整体更新；字段有变化写 `kind='edit'` 履历 |
| DELETE | `/customers/{id}` | 不变（仅无关联时可删） |
| GET | `/customers/{id}/addresses` | ★ 新增 |
| POST | `/customers/{id}/addresses` | ★ 新增（`is_default` 唯一：置 1 时把同客户其它置 0） |
| PUT | `/customers/{id}/addresses/{aid}` | ★ 新增 |
| DELETE | `/customers/{id}/addresses/{aid}` | ★ 新增（被订单 `address_id` 引用时只置 `NULL`，订单快照不受影响） |
| GET | `/tags` | 不变 |

### 5.5 商机 `/deals`

| 方法 | 路径 | 变更 |
|---|---|---|
| GET | `/deals` | 出参加 `drive_type(_label)`、`model`、`spec`、`note`、`order_id`、`locked`、`customer_name`；**不再返回 `title`**（G-20） |
| GET | `/deals/{id}` | ★ 出参 `timeline[]`（`[{at,type,type_label,content,files[],detail}]`，`at` 倒序）、`materials[]`、`order{...}`\|null、`locked` |
| POST | `/deals` | 入参加 `drive_type`(必填)、`note`；`model` 走字典校验；`spec` 可空但 `model` 能带出尺寸；`stage` 固定 `quote` |
| PUT | `/deals/{id}` | ★ 允许改 `product_type/model/spec/drive_type/amount/note/stage`；**`locked` 时除 `note/stage` 外一律 409 `deal_locked`**；有变化写 `kind='edit'`，阶段变化额外写 `kind='stage'` |
| POST | `/deals/{id}/orders` | ★ **新增**：生成订单（§5.6），前置 `stage='won'` |
| POST | `/deals/{id}/win` | **保留兼容**：内部转调 `/orders`（无 payload 时押金 = 金额、物流方式 `self`、运费 0、无收货地址） |
| POST | `/deals/{id}/lose` | 不变（`lost_reason` 必填） |

**`POST /deals/{id}/orders` 入参**

```jsonc
{
  "amount": 12000.0,          // 默认 = deals.amount，可改
  "deposit": 20000.0,         // 必填，0 ≤ deposit ≤ amount；balance 由服务端算（Q-D 恒等式）
  "logistics_mode": "agent",  // free|agent|self
  "carrier_id": 2,            // agent/free 时必填；self 时忽略
  "logistics_fee": 800.0,     // free/self 默认 0，可改
  "address_id": 3,            // 客户地址簿 id；不传则用下面三项新建并回存地址簿
  "receiver_name": "陈国强", "receiver_phone": "137…", "receiver_address": "潍坊…",
  "tracking_number": null,    // 可后补
  "note": "月底前发货"
}
```

**事务内动作（缺一不可）**：① 建订单（`balance_amount = amount - deposit`、`status='pending_payment'`、收货三项**快照**写入）② 商机 `stage='won'`、`closed_at`、`order_id`、`locked_at` ③ `follow_ups` 写 `kind='order'` ④ `order_status_log` 写 `event_type='order'` ⑤ `carriers` 关联次数由 SQL 实时算，不落库。

**错误码**：`deal_not_found`(404) / `deal_not_won`(409, "先把阶段推进到成交") / `deal_locked`(409) / `order_exists`(409) / `invalid_deposit`(400) / `carrier_required`(400)。

### 5.6 订单 `/orders`

| 方法 | 路径 | 变更 |
|---|---|---|
| GET | `/orders` | 出参加 `deposit_amount`、`balance_amount`、`deposit_paid`、`balance_paid`、`logistics_mode(_label)`、`logistics_fee`、`carrier_name`、`receiver_*`、`status_label` |
| GET | `/orders/{id}` | ★ `timeline[]`（`[{at,type,type_label,content,from_status,to_status,amount,screenshots[]}]`，与 §5.5 同结构）+ `deal`（可点回）+ `aftersales[]`（**无售后则返回 `[]`，前端整块隐藏**）+ `carrier_contacts[]` |
| POST | `/orders` | 固定 405（订单只能由商机生成） |
| PUT | `/orders/{id}` | 允许改 `tracking_number/receiver_*/note`；收货信息变化写 `event_type='address'` |
| POST | `/orders/{id}/transition` | 7 态机不变；`shipped` 需 `tracking_number`；每次写 `event_type='stage'` |
| POST | `/orders/{id}/pay-deposit` | ★ 入参 `{amount, note, screenshots[]}`；**`amount` 必须等于 `deposit_amount`**，否则 400 `amount_mismatch`「押金应收 ¥X，实收 ¥Y」；已收过押金再调 → 409 `already_paid`；写 `event_type='pay'` |
| POST | `/orders/{id}/pay-balance` | 同上，对 `balance_amount`；尾款必须在押金已收之后收（`deposit_paid < deposit_amount` → 409 `deposit_unpaid`） |
| GET | `/orders/{id}/status_log` | 保留（等价于 `timeline` 的 `type='stage'` 子集） |

**订单号**：`SO-YYYYMMDD-NNN`（当日序号，事务内 `MAX+1`，`next_no` 内部规整日期，见 G-05）。

### 5.7 跟进 / 履历 / 附件

| 方法 | 路径 | 变更 |
|---|---|---|
| POST | `/follow-ups` | ★ multipart：`files` 任意类型 **≤10 个、单个 ≤20MB**；`next_date` 可空（开关关 = 不传）；`method` 只收 `wechat/phone`（默认 `wechat`）；创建成功写 `kind='follow'`；对象是售后且状态 `done` → 409 `aftersale_closed`；对象是售后且 `pending` → 自动置 `processing` + 状态日志 |
| GET | `/follow-ups?object_type=&object_id=&deal_id=&customer_id=` | ★ 出参 `type`/`type_label`/`detail`/`files[]`（含 `is_image`/`url`/`size`/`name`）；时间倒序（DB 列仍是 `kind`，出参统一叫 `type`） |
| DELETE | `/follow-ups/{id}` | 只允许删 `kind='follow'` 且本人 1 小时内（沿用现有规则）；系统履历不可删（409 `system_entry`） |
| GET | `/follow-ups/materials?object_type=&object_id=&deep=true` | ★ **新增**（资料汇总卡）：该对象所有 `kind='follow'` 的附件；`deep=true`（客户）额外包含其商机/售后的跟进附件；按时间倒序 |
| GET | `/attachments/{id}` | ★ 任意类型下载：`Content-Disposition: attachment; filename*=UTF-8''…` + `X-Content-Type-Options: nosniff`；图片仍可 `?inline=1`（仅 `image/*`） |

### 5.8 售后 / 物流

| 方法 | 路径 | 变更 |
|---|---|---|
| POST | `/aftersales` | 前置：订单必须 `status='completed'`，否则 409 `order_not_completed`；写订单 `event_type='aftersale'` |
| GET | `/aftersales`、`/aftersales/{id}` | 出参加 `timeline[]`、`order_no`、`customer_name`、`sla_days_left` |
| POST | `/aftersales/{id}/finish` | 入参 `{result}`；仅 `processing→done`；写状态日志 + `kind='status'` 履历 |
| POST | `/aftersales/{id}/start` | **下线**：返回 410 `deprecated`「记一条跟进后自动进入处理中」 |
| POST | `/aftersales/{id}/reject` | **下线**：返回 410 `deprecated`「售后不再支持拒绝」 |
| GET/POST | `/carriers` | 出参 ★ `contacts[]`（`name/phone/tags[]`）+ `order_count`；入参接受 `contacts[]` 整体覆盖 |
| PUT/DELETE | `/carriers/{id}` | 被引用 >0 → DELETE 409 `carrier_in_use`（已有，保留） |

### 5.9 统计 `GET /stats?months=6`（G-17，新增）

**出参形状按 demo `stats.js` 现成渲染结构给**（前端只改数据源，不改渲染逻辑）：

```jsonc
{
  "kpis": {"customers_total":10,"month_new_customers":2,"month_won":{"count":3,"amount":46500.0},
           "active_deals":5,"repeat_customers":3,"pending_aftersales":1},
  "months": [{"label":"5月","value":0,"highlight":false}, …6 条…],          // 近 6 月成交额
  "funnel": [{"label":"报价","value":13},{"label":"待客户确认","value":9},{"label":"成交","value":7}],  // 累计到达
  "lead_conversion": {"total":5,"following":2,"converted":1,"invalid":1,"rate":20.0},
  "deals_by_stage": [{"label":"报价","value":2,"cls":""},…],
  "orders_by_status": [{"label":"待支付","value":1},…7 条…],
  "customer_sources": [{"label":"微信","value":4},…],
  "aftersale_types": [{"label":"维修","value":1},…]
}
```

**口径**（写进 SQL 注释，评审逐条对）：

1. 漏斗「累计到达」：`stage='won'` 计 3 段全到；`confirm` 计前 2 段；`quote` 计 1 段；`lost` **不计入漏斗**；
2. 线索转化率分母 = 线索池总数，`rate = converted / total * 100`（不会 >100%）；
3. 「本月」= `date('now','localtime')` 的自然月，禁 UTC；
4. 「老客/复购」= 该客户商机数 ≥2；
5. 金额一律 `ROUND(SUM(amount),2)`，前端负责遮罩。

### 5.10 数据字典 `/dicts`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/dicts` | 12 张总览：`[{code,name,level,desc,items:[{key,label,sort,enabled,used}]}]` |
| GET | `/dicts/{code}` | 单张（`#/dict/{code}` 深链用） |
| POST | `/dicts/{code}/items` | **仅 A 类**：`{key,label,sort,enabled,meta}`；key 校验 `^[a-z0-9_-]{1,32}$` 且不重复（409 `dict_key_exists`）；B/C/D → 403 `dict_level_forbidden` |
| PUT | `/dicts/{code}/items/{key}` | A/B/C 可改 `label/sort/enabled`；**key 不可改**（400 `dict_key_immutable`）；D 类 403 |
| DELETE | `/dicts/{code}/items/{key}` | **仅 A 类且 `used=0`**；否则 409 `dict_item_in_use` |
| GET | `/dicts/product_model?q=XW&product=天窗` | 型号可搜索（前端下拉用），匹配 `key`/`label`/`meta.size` |

**改字典的影响面**：`enabled=0` 后新建下拉消失，历史记录照常显示；`label` 改动全站文案立即变（`lru_cache` 清空）。---

## 6. 业务规则与 SQL 口径

> 这一节是给 reviewer 的「对错标准」。凡是口径问题，一律以本节 SQL/伪码为准，不看前端怎么显示。

### 6.1 待跟进 / 逾期（G-11，唯一实现）

```sql
-- 每个客户只看「最近一条真实跟进」的 next_date
WITH latest AS (
  SELECT object_type, object_id, next_date, created_at,
         ROW_NUMBER() OVER (
           PARTITION BY object_type, object_id
           ORDER BY datetime(created_at) DESC, id DESC
         ) AS rn
  FROM follow_ups
  WHERE kind = 'follow'
    AND object_type IN ('lead', 'customer', 'deal')
    AND next_date IS NOT NULL AND TRIM(next_date) <> ''
)
SELECT l.object_id AS customer_id, c.name, l.next_date, l.created_at AS last_follow_at,
       CAST(julianday(date('now','localtime')) - julianday(date(l.next_date)) AS INTEGER) AS days_overdue
FROM latest l
JOIN customers c ON c.id = l.object_id
WHERE l.rn = 1
  AND date(l.next_date) <= date('now','localtime')
  AND NOT EXISTS (SELECT 1 FROM deals d WHERE d.customer_id = c.id AND d.stage IN ('won','lost') AND d.order_id IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM deals d WHERE d.customer_id = c.id AND d.stage NOT IN ('won','lost'))
ORDER BY date(l.next_date) ASC, c.id ASC;
```

**判定规则（照抄 PAGES §1.2）**：

- 取该客户**最近一条** `kind='follow'` 的 `next_date`；为空 → **不入列**（开关关掉就是不提醒）；
- `days_overdue = today − next_date`：`0` = 今天到期（不算逾期，但进「今日待跟进」）；`>0` = 逾期 N 天（整行标红）；
- **以这条跟进自己关联的商机为准**：该商机已 `won`/`lost` → 不提醒；跟进**不挂商机**（纯客户回访，如安装回访/老客维护）→ 照常提醒；
- **同客户记了新跟进（next_date 更晚）后，旧记录自动退出列表**（这是本条的关键验收点）。

### 6.2 商机锁定（G-04）

| 场景 | 结果 |
|---|---|
| `stage != 'won'` 调 `POST /deals/{id}/orders` | 409 `deal_not_won` |
| 已 `order_id` 非空再调 | 409 `order_exists` |
| `locked` 后 `PUT /deals/{id}` 改 `amount/spec/model/drive_type/product_type` | 409 `deal_locked` |
| `locked` 后改 `note`、推进 `stage`、记跟进、传附件 | **允许**（业务上还要跟安装/尾款/售后） |
| `locked` 后判流失 | 409 `deal_locked`（已下单不能流失；要退单走售后） |

### 6.3 订单收款与状态机（不变部分照旧）

- 7 态机 `ORDER_FLOW` 不变，`transition` 只允许走下一态，跳态 409 `invalid_transition`；
- **恒等式（Q-D 决议，硬约束）**：`amount = deposit_amount + balance_amount`，且 `amount = deposit_paid + balance_paid` 才能标记完成。
  - 生成订单：`deposit_amount` 必填（`0 ≤ deposit ≤ amount`，等于 amount 即全款），`balance_amount` **服务端强制** `= amount − deposit_amount`，前端传什么都不采信；
  - 改 `amount` 或 `deposit_amount`（未收款前允许改）：在同一事务里**重算** `balance_amount`，并校验已收款不超过新值（`deposit_paid > deposit_amount` → 409 `paid_exceeds_due`）；
  - 收款：`amount` 必须**等于**对应应收（`deposit_amount` / `balance_amount`），不等即 400 `amount_mismatch`，**不做 warnings、不落半截数据**；
  - 完成：`completed` 前置校验 `deposit_paid = deposit_amount AND balance_paid = balance_amount`，否则 409 `payment_incomplete`「还差 ¥N 未收」；
  - 定金为 0（`deposit_amount=0`）时跳过收押金，直接收尾款；
- `pay-deposit` / `pay-balance` 支持 `screenshots[]`（图片，≤3 张），写入 `attachments.object_type='order_payment'`；
- `shipped` 必须已有 `tracking_number`（可后补，但发货时必须填）；
- 订单完成后才能加售后（`order_not_completed`）；
- 订单没有售后单时，详情出参 `aftersales: []`，**前端整块不渲染**。

### 6.4 售后流转（G-18）

```
pending ──记一条跟进──▶ processing ──标记完成(二次确认)──▶ done
   │                        │
   └────────────────────────┴── done 之后：禁止再加跟进 / 禁止任何状态变更
```

- 只保留 3 态；`rejected` 仅作为历史值可读（新代码不可写入）；
- `POST /aftersales/{id}/start`、`/reject` 返回 410 + 中文提示（前端已无按钮，留着防旧书签）；
- `done` 时写 `result` + `closed_at` + `aftersale_status_log` + `follow_ups(kind='status')`；
- 需要再修 → **另开一单售后**（不提供「重新打开」）。

### 6.5 附件上传安全（G-09）

| 项 | 规则 |
|---|---|
| 允许类型 | 图片（jpg/jpeg/png/gif/webp/bmp/heic/heif）+ `pdf` + `xls/xlsx` + `doc/docx` + `dwg/dxf` + `zip` |
| 单文件上限 | 20 MB（`MAX_FILE_BYTES`），超限 400「xx 超过 20MB」 |
| 单条上限 | 10 个，超出部分**不落盘**并返回 `skipped[]`（前端已按此提示） |
| 类型判定 | 扩展名白名单 **+ `mimetypes` 嗅探**，两处都过才算；`.html/.svg/.js/.php` 一律拒（400） |
| 落盘 | 沿用 `storage_key = YYYY/MM/DD/<uuid>.<ext>`，路径逃逸校验不变 |
| 下载 | 非图片强制 `attachment`；图片可 `?inline=1`；统一 `nosniff` |
| 目录 | 仍为本地 `uploads/`，纳入每日备份（不上 MinIO） |

### 6.6 字典缓存与生效

- 进程内 `lru_cache` 缓存「code→{key:label}」，任何写操作后 `cache_clear()`；
- 单进程 uvicorn + 单用户，不存在多进程缓存不一致；
- 改显示名**不需要发版、不需要重启**。

### 6.7 时间口径（沿用 V2，不改）

- `created_at/updated_at`：UTC ISO（`…Z`），由 `security.now_iso()` 写；
- 业务日期（`next_date`、`closed_at`、`shipped_at`）：**本地无时区**（`now_local_iso()` / `YYYY-MM-DD`）；
- 统计与「本月」一律 `date('now','localtime')`；**禁止** UTC 换算跨零点。

---

## 7. 迁移 / 发布 / 回滚

### 7.1 版本与顺序

| 步骤 | 内容 | 谁做 |
|---|---|---|
| 1 | 备份库 + uploads | @ops（`ops/backup.py` 或 `cp crm.db backups/crm-pre-v3-$(date +%Y%m%d-%H%M).db`） |
| 2 | `v2_002` 迁移（启动时自动跑，`app/migrations.py`） | @coder 交付 |
| 3 | 后端发布（`systemctl restart crm-api`） | @ops |
| 4 | 前端发布（`bash ops/deploy-frontend.sh`）+ `sw.js` 版本号 +1 | @ops |
| 5 | 冒烟（§9.5）+ 全量回归 | @reviewer |

### 7.2 迁移脚本 `v2_002`（结构）

```python
# app/migrations.py 追加
V2_002 = "v2_002"

def migrate_v2_002(conn):
    """CRM V2 定稿（前端 frontend-final-v2.7）对齐迁移。

    全部 ADD COLUMN / CREATE TABLE IF NOT EXISTS；不重建、不删列。
    幂等：靠 schema_migrations 落账 + IF NOT EXISTS。
    """
    todo = [
        # ① 三张新表
        "CREATE TABLE IF NOT EXISTS customer_addresses (...)",
        "CREATE TABLE IF NOT EXISTS carrier_contacts (...)",
        "CREATE TABLE IF NOT EXISTS dict_items (...)",
        # ② 扩列（SQLite 单列 ADD，可重复执行前先查 pragma 兜底）
        "ALTER TABLE customers ADD COLUMN house_type TEXT",
        # ... 共 7 + 3 + 7 + 2 + 2 列
        # ③ 索引
        "CREATE INDEX IF NOT EXISTS idx_addr_customer ON customer_addresses(customer_id)",
        # ...
    ]
    for sql in todo:
        conn.execute(sql)
    # ④ 种子 + 值域迁移（同一事务内）
    seed_dict_items(conn)                       # 11 张 + product_model 30 条
    conn.execute("UPDATE orders SET logistics_mode='agent' WHERE logistics_mode='carrier'")
    conn.execute("UPDATE deals SET stage='confirm' WHERE stage='negotiate'")
    conn.execute("UPDATE deals SET stage='quote' WHERE stage IN ('lead','quoted')")
    conn.execute("INSERT INTO schema_migrations VALUES ('v2_002', datetime('now'), 'V2 定稿对齐')")
```

**执行守卫（已踩过的坑，必须保留）**：`app/migrations.py` 现有「按 `;` 切分语句」的实现**遇到触发器/多语句会截断** —— 新迁移里不要放 `CREATE TRIGGER` 多语句块；确需触发器时用 `conn.executescript()` 单块执行。

**每步验证（跑完立刻执行，全绿才继续）**：

```bash
cd /opt/data/crm
python3 - <<'PY'
import sqlite3; c=sqlite3.connect('crm.db')
print(c.execute("PRAGMA integrity_check").fetchone())
print(c.execute("PRAGMA foreign_key_check").fetchall())
print(c.execute("select version from schema_migrations").fetchall())
print(c.execute("select count(*) from dict_items").fetchone())          # 期望 = 77（11 张系统字典 47 条 + 型号 30 条）
print(sorted(r[1] for r in c.execute("pragma table_info(orders)")))      # 含 7 个新列
print(c.execute("select stage,count(*) from deals group by stage").fetchall())
PY
```

### 7.3 发布命令（照抄，别自创）

```bash
# 后端
cd /opt/data/crm
ADMIN_PASSWORD=test123 CRM_DB=/tmp/crm-v3-$(date +%s).db env -u PYTHONPATH -u VIRTUAL_ENV \
  /usr/bin/python3 -m unittest discover -s tests -v      # 全绿才发
systemctl restart crm-api && sleep 2 && systemctl is-active crm-api
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/api/crm/health

# 前端（nginx 读的是 /root/nginx/html/crm，不是源码目录）
bash ops/deploy-frontend.sh
curl -s http://<内网服务器IP>:8000/crm/ | grep -o 'app.js?v=[0-9]*'      # 版本号应为新值
```

### 7.4 回滚

| 层 | 手段 | 影响 |
|---|---|---|
| 前端 | `git checkout frontend-final-v2.7 -- static && bash ops/deploy-frontend.sh` | 秒级，只回页面 |
| 后端代码 | `git checkout <上一 commit> -- app/ && systemctl restart crm-api` | 1 分钟 |
| 数据库 | 停服 → `cp backups/crm-pre-v3-*.db crm.db` → 起服 | 1 分钟，**丢当日录入** |
| 单条迁移 | 只回滚代码不回滚库时，新列留着不影响旧代码（全是可空列 + 新表） | 安全 |

> 关键设计保证：`v2_002` **只有 ADD COLUMN / CREATE TABLE**，所以「代码回滚、库不回滚」永远安全。这也是本轮不做「改类型/重建表」的原因。

---

## 8. 正式前端接管（G-21 / G-22）

### 8.1 文件动作

| 文件 | 动作 |
|---|---|
| `static/demo/views/*.js` → `static/views/` | 以 demo 版为基线覆盖 10 个视图（`dashboard/leads/customers/deals/followpage/orders/aftersales/logistics/stats/dict`）；**但必须先做 §8.2 的数据源改造**，见下方实测 |
| `static/demo/core.js` | 工具函数、`STAGES`/`ORDER_STATUS`/`LOGISTICS_MODES`/`RECORD_META` 等常量搬进 `app.js`（单一文件，避免两套常量漂移） |
| `static/app.js` 的 `api()` | 换成真实 `fetch(API_BASE + path, {credentials:'include'})`；`mockGet/mockWrite` 删除 |
| `static/views/import.js` | **删除**：导入并入线索页（PAGES §7.3） |
| `static/demo/` | **保留**作为「设计稿」，`index.html` 加 `noindex`，日常入口只认 `/crm/` |
| `static/sw.js` | `CACHE_VERSION` +1（v2 → v3），确保旧页面不被缓存住 |
| `static/index.html` | 导航改 9 项（工作台/线索/客户/商机/订单/售后/物流/统计/数据字典）+ 顶栏 👁 金额开关 |

> ⚠️ **实测修正（别按「只换 api()」估算）**：demo 视图里只有 `dashboard.js`、`dict.js` 走了 `api()`，
> 其余 8 个视图**直接读 `window.DEMO.*`**，共 **93 处**（`deals.js` 36、`stats.js` 23、`customers.js` 14、
> `orders.js` 13、`logistics.js` 8、`leads.js` 7、`aftersales.js` 6、`dashboard.js` 2），写操作走 `mockWrite` 假成功。
> 所以 T8 的真实工作量 = **把 93 处直读改成接口调用 + 把假成功改成真写**，不是换一个函数。

### 8.2 改造顺序（照此做，别反）

**第一步：视图数据源（93 处，逐视图过）**

| 视图 | 改造 | 主要接口 |
|---|---|---|
| `leads.js` | `window.DEMO.leads` → `GET /leads`；新增/编辑/导入 → `POST/PUT`；转商机 → `POST /leads/{id}/convert` | §5.3 |
| `customers.js` | → `GET /customers`、`GET /customers/{id}/360`、`PUT`（含 profile） | §5.4 |
| `deals.js` | → `GET /deals`、`GET /deals/{id}`（timeline）；新建/编辑 → `POST/PUT`；生成订单 → `POST /deals/{id}/orders`；**生成订单按钮：押金合法且「押金+尾款=总额」成立才可点**（Q-D 硬约束） | §5.5 |
| `orders.js` | → `GET /orders`、`GET /orders/{id}`；收款 → `pay-deposit|pay-balance`；推进 → `transition` | §5.6 |
| `aftersales.js` | → `GET /aftersales`；完成 → `POST /aftersales/{id}/finish`；新建只从订单页调 | §5.8 |
| `logistics.js` | → `GET/POST/PUT/DELETE /carriers`（`contacts[]` 整体提交） | §5.8 |
| `followpage.js` | 数据由调用方传入 → 改为自己 `GET /follow-ups?...&object_type=`；记一条 → `POST /follow-ups`（multipart） | §5.7 |
| `stats.js` | `window.DEMO` → `api('/stats?months=6')`，渲染代码不动 | §5.9 |
| `dashboard.js` | 已在用 `api('/dashboard')`，只对齐出参（`in_progress_deals`/`recent_activities`） | §5.2 |
| `dict.js` | 已在用 `api('/dicts')`，补写操作 4 个端点 | §5.10 |

**第二步：`app.js` 必改的 4 处**

1. **枚举来源**：`STAGES`/`SOURCE_LABELS` 等从 `GET /dicts` 灌入（启动时一次），失败时退回内置常量；
2. **金额遮罩**：`state.showMoney` 默认 `false`，顶栏 👁 切换，**切页面保持**（内存态，不写 localStorage）；
3. **路由表**：13 条（PAGES §8），`#/deals/{id}` 同时承载商机跟进页；
4. **错误提示**：统一吐 `message` 字段（中文），401 跳登录。

**第三步**：`RECORD_META`（履历类型图标/中文）必须与 §1.1 `TIMELINE_TYPE` 同值域，缺一个就渲染成「跟进」。

### 8.3 `stats.js` 只改数据源

demo 版直接读 `window.DEMO`；正式版把开头两行换掉，渲染代码不动：

```js
// demo:  var D = window.DEMO;  …各种 filter/reduce 现算
// 正式:  api('/stats?months=6').then(render(已算好的 8 块))
```

`GET /stats` 出参形状必须与 `stats.js` 现算的中间变量同名同结构（§5.9），**否则前端要改渲染，等于又做一遍**。
这也是 `/stats` 放在 SQL 里算、而不是前端 filter 的原因：数据量上来后前端全表拉取会卡。

### 8.4 缓存与验收

`bash ops/deploy-frontend.sh` 末尾的自检会校验 `API_BASE` 绝对路径、登录表单 `autocomplete`、无 `localStorage` 写入 —— 三项任一失败即打回。

---

## 9. 测试与验收

### 9.1 环境前缀（所有测试命令都带这三行口径）

```bash
cd /opt/data/crm
export ADMIN_PASSWORD=test123
export CRM_DB=/tmp/crm-t-$$.db          # 严禁指向 /opt/data/crm/crm.db（_bootstrap.py 会直接抛错）
env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -m unittest discover -s tests -v
```

### 9.2 旧用例影响（已知要改的断言）

| 影响点 | 实测命中 | 处理 |
|---|---|---|
| `confirm`（阶段语义/默认值） | 5 个文件 17 处 | 改断言：默认 `quote`；「需求确认」→「待客户确认」 |
| `photos` / 「最多 3 张」 | 2 个文件 12 处 | 改 10 个；非图片从「400 拒绝」改为「允许」 |
| `rejected`（售后拒绝） | 3 个文件 6 处 | 改断言：`/reject` → 410 |
| `/start`（售后开始处理） | 1 个文件 8 处 | 改断言：410 + 「记跟进自动处理中」 |
| `title`（商机未命名） | 1 个文件 18 处 | 从 `DealOut` 移除 `title` 后，断言改为不返回 |

> 目标：**182 条旧用例 → 全部转绿（允许改断言，不允许删覆盖）**，另加 §9.3 新增用例。

### 9.3 新增测试文件（目标 102 条）

| 文件 | 覆盖 | 目标条数 |
|---|---|---|
| `tests/test_dicts.py` | 12 张字典、A/B/C/D 越权 403、key 不可改、被引用不可删、改名即时生效、型号搜索 | 22 |
| `tests/test_deal_orders.py` | 非成交阶段 409、生成订单全字段落库、押金/尾款恒等式（含全款/押金 0/改金额重算）、锁定后改字段 409、履历 5 类齐全 | 24 |
| `tests/test_order_timeline.py` | 6 类事件写入、时间线排序、改收货写 address、发货需运单号、收款金额不符 400 / 重复收 409 / 未收齐不许完成 409 | 18 |
| `tests/test_addresses_contacts.py` | 地址簿 CRUD + 默认地址唯一 + 下单快照 + 地址被删不影响历史单；多联系人 + 标签 + 被引用不可删 | 16 |
| `tests/test_files.py` | 任意类型上传、20MB 边界、10 个上限、`.html/.svg` 拒绝、下载 `attachment`+`nosniff` | 14 |
| `tests/test_stats_workbench.py` | 待跟进按最近一条（旧记录消失）、8 块统计口径、漏斗累计到达、线索转化 ≤100% | 10 |

### 9.4 验收断言表（reviewer 一行一个，逐条对 G）

| # | 断言（可执行的口径） | 反查 G |
|---|---|---|
| A01 | 新建商机 `stage` 默认 `quote`，`stage_label` = 「报价」 | G-01 |
| A02 | 阶段枚举只有 4 个，`negotiate` 传值 → 400 | G-01 |
| A03 | 新建商机不传 `drive_type` → 400；传 `manual/electric` → 落库并出 `_label` | G-02 |
| A04 | `stage='quote'` 调 `POST /deals/{id}/orders` → 409 `deal_not_won` | G-04 |
| A05 | 生成订单后 `deals.locked=true`、`order_id` 非空、`stage='won'` | G-03 |
| A06 | 订单号匹配 `^SO-\d{8}-\d{3}$` | G-05 |
| A07 | `deposit=20000, amount=12000` → 400；正常单 `balance_amount = amount - deposit` | G-08 |
| A08 | `logistics_mode` 只接受 `free/agent/self`；`carrier` → 400 | G-06 |
| A09 | 生成订单只用 `address_id` 时，`receiver_*` 被快照；随后改地址簿，订单详情的收货信息**不变** | G-07/G-15 |
| A10 | 一条跟进传 11 个附件 → 前 10 个入库，返回 `skipped` 1 条 | G-09 |
| A11 | 传 `.xlsx` / `.pdf` 成功；传 `.html` → 400 | G-09 |
| A12 | 下载非图片响应头含 `Content-Disposition: attachment` 与 `X-Content-Type-Options: nosniff` | G-09 |
| A13 | 商机详情 `timeline` 含 `create/change/stage/order` 四类（造一条全流程数据） | G-10 |
| A14 | 订单详情 `timeline` 含 `order/pay/stage/ship/address/aftersale` 六类 | G-10 |
| A15 | 客户最新跟进 next_date=11-05、旧记录 next_date=10-31 → 工作台**不含**该客户 | G-11 |
| A16 | 最新跟进 next_date=昨天但为空（开关关）→ 工作台**不含** | G-11 |
| A17 | 字典加「抖音」后 `GET /dicts/customer_source` 立即含它，且新建客户可选 | G-12 |
| A18 | `deal_stage` 新增项 → 403；改名「赢单」→「成交」后所有商机 `stage_label` 变「成交」 | G-12 |
| A19 | 被 3 条数据引用的来源删除 → 409 `dict_item_in_use` | G-12 |
| A20 | `GET /dicts/product_model?q=1200` 返回含 1200 尺寸的型号；选中带出 `spec` | G-13 |
| A21 | `GET /stats` 8 个字段齐全，`funnel` 3 段且 `lost` 不计入 | G-17 |
| A22 | 售后 `pending` 记一条跟进 → 状态自动 `processing`，且无「开始处理」调用 | G-18 |
| A23 | 售后 `done` 后 `POST /follow-ups` → 409 `aftersale_closed` | G-18 |
| A24 | 订单未 `completed` 调 `POST /aftersales` → 409 `order_not_completed` | G-18 |
| A25 | 线索列表出参含 `last_follow_at` 与 `days_overdue` | G-19 |
| A26 | `GET /deals/{id}` 不含 `title` 字段 | G-20 |
| A27 | 物流公司 2 个联系人带 tags，`carriers` 出参 `contacts[].tags` 正确 | G-16 |
| A28 | 数据字典 12 张、`product_model` 30 条种子 | G-12 |
| A29 | `/crm/` 首页导航 9 项，`#/dict` 可打开，`#/stats` 有 8 块 | G-21 |
| A30 | 金额默认遮罩 `¥••••`，点 👁 显示真值，切页面保持 | PAGES §0.3 |
| A31 | 生成订单后 `deposit_amount + balance_amount == amount`（含全款、押金 0 两种边界） | Q-D |
| A32 | 收押金传错金额 → 400 `amount_mismatch`，且订单状态与已收金额**都没变** | Q-D |
| A33 | 只收押金就调 `transition → completed` → 409 `payment_incomplete`；收齐后才成功 | Q-D |
| A34 | 未收款前把 `amount` 从 12000 改 13000 → `balance_amount` 自动变，等式仍成立 | Q-D |

### 9.5 手工冒烟（浏览器 10 分钟，上线前必做）

1. 登录 → 工作台：5 个数字卡有数、待跟进逾期红色、点卡片跳筛选后的列表；
2. 线索 → 新增（意向默认「中」）→ 转商机（手动/电动必填、型号搜索 `XW`）→ 商机阶段「报价」；
3. 商机 → 编辑（改尺寸 → 履历出现「编辑」）→ 推进到「成交」→ 生成订单（押金 20000、代办、运费 800、选历史地址）；
4. 订单 → 收押金（2 张截图）→ 推进到已完成 → 时间线 6 类事件齐全 → 加售后；
5. 售后 → 记一条跟进（自动处理中）→ 标记完成（二次确认）→ 再加跟进被拒；
6. 更多→数据字典 → 加来源「抖音」→ 回线索页下拉可见；改「商机阶段」显示名 → 全站文案变；
7. 统计 → 8 块图有数，漏斗不出现 >100%；
8. 手机竖屏（375px）走一遍：无横向滚动、模态框按钮可点、图片点开是大图。

---

## 10. 任务拆解（@coder 按序开工）

### 10.1 依赖图

```
T1 枚举+字典基座 ──┬─▶ T3 商机/生成订单 ──┬─▶ T5 跟进/附件/履历 ──▶ T8 前端接管 ──▶ T9 回归上线
T2 迁移 v2_002  ──┘   T4 订单/物流/地址簿 ─┘   T6 售后
                                          └─▶ T7 工作台/统计/线索
```

### 10.2 任务卡

| 卡 | 内容 | 交付物 | 估时 | 依赖 |
|---|---|---|---|---|
| **T1** | 枚举值域改造 + `app/dicts.py` 注册表 + `routers/dicts.py` + 字典校验函数 | 6 个端点、`dict_items` 读写 | 1.5 人日 | — |
| **T2** | `v2_002` 迁移 + 种子 + 值域 UPDATE + 索引；副本库实测 | 迁移脚本 + 实测输出 | 1 人日 | T1（种子依赖注册表） |
| **T3** | 商机字段/阶段/锁定 + `POST /deals/{id}/orders` + 履历写入 + 订单号修复 | 契约 §5.5 | 2 人日 | T1,T2 |
| **T4** | 订单扩列/收款拆项/时间线 + 地址簿 + 物流多联系人 + 运费/收货 | 契约 §5.6、§5.8 | 2 人日 | T2 |
| **T5** | 任意类型附件（≤10/20MB/嗅探/防内联）+ `kind` 履历 + 资料汇总卡 + 售后自动处理中 | 契约 §5.7 | 2 人日 | T3 |
| **T6** | 售后 3 态收口：下线 start/reject、finish、done 锁定 | 契约 §5.8、§6.4 | 0.5 人日 | T5 |
| **T7** | 工作台改造（5 卡 + 动态 + 逾期口径）+ `/stats` 8 块 + 线索列表派生字段 | 契约 §5.2、§5.9、§5.3 | 1.5 人日 | T2 |
| **T8** | 正式前端接管：覆盖 10 个视图 + **93 处 `window.DEMO` 直读改接口** + 假写改真写 + 字典驱动下拉 + 金额遮罩 + `sw.js` 升版 | `/crm/` 与 demo 视觉一致且数据来自后端 | 4 人日 | T3–T7 |
| **T9** | 全量回归（182 旧 + 102 新）+ 迁移验收 + 冒烟 + 发布 + 回滚演练 | 验收记录 | 1 人日 | 全部 |

**合计 ≈ 15.5 人日**（1 人顺序做，含 20% 缓冲 ≈ 19 人日）。最高风险卡：**T5**（附件放开 + 履历双写）与 **T8**（93 处前端改造，容易漏视图），建议各单独一轮 review。

### 10.3 交付纪律

- 每张卡完成即跑 `unittest discover`，**不允许攒到最后一起跑**；
- 改动 `enums.py` 的卡（T1/T3）必须同步 `static/app.js` 常量，否则前端先崩；
- 卡片关闭前必须贴「实际命令输出」，不接受"应该没问题"。

---

## 11. 风险与待拍板

### 11.1 风险登记

| # | 风险 | 触发条件 | 规避 |
|---|---|---|---|
| R1 | `confirm` key 语义漂移 | 旧前端/旧测试仍按「需求确认」理解 | 本轮同批升级前端（T8 与 T3 同一个发布窗口），旧 demo 标注只读 |
| R2 | 字典与 `Literal` 双源漂移 | A 类加了值但 `Literal` 没放开，或反之 | B/C/D 只走 `Literal`；A 类只走字典；测试 A18 静态守住 |
| R3 | 上传目录被塞可执行文件 | 白名单漏配 `.svg/.html` | §6.5 双层校验 + 下载强制 attachment；测试 A11/A12 |
| R4 | 履历双写导致重复条目 | 编辑保存时误判「有变化」 | 只比较白名单字段且 `from != to` 才写；测试 A13 |
| R5 | 待跟进 SQL 性能 | 窗口函数在 10⁵ 行上全表扫 | `idx_fu_obj(object_type,object_id,created_at)` 已建；实测 >50ms 再加物化 |
| R6 | 订单锁死但业务要改单 | 客户改地址/加急 | `PUT /orders/{id}` 保留收货/运单可改 + 写 `address` 事件 |
| R7 | 前端缓存导致看到旧页面 | `sw.js` 未升版 | 每次前端发布 `CACHE_VERSION` +1；验收看 `app.js?v=` |
| R8 | 迁移半途失败 | 多语句被截断 | 全部幂等 SQL + 事务 + `executescript`；失败即回滚备份 |
| R9 | 前端接管被低估 | 以为「只换 `api()`」，实际 93 处直读（实测） | §8.2 按视图逐张过；每张卡完成即用真实后端点一遍该页；验收 A29/A30 |

### 11.2 Q-A…Q-D 拍板决议（用户确认，2026-10-31，**实现按此，不再讨论**）

| # | 问题 | 决议 |
|---|---|---|
| Q-A | 型号带出的尺寸能否手改、统计按哪个算 | ✅ **允许手改；统计口径一律按 `deals.spec`（实际尺寸）**。型号只负责带出初值与筛选，不参与统计 |
| Q-B | 售后 `rejected` 历史值处置 | ✅ **保留可读、不可写入**，页面不显示该状态 |
| Q-C | 金额遮罩记忆范围 | ✅ **仅会话内记忆**，重新登录恢复遮罩 |
| Q-D | 收款金额与应收不一致怎么办 | ✅ **不存在「不一致」这种情况**：订单金额必须恒等于「押金 + 尾款」，见 §6.3 三条强制校验（改金额/改押金→重算尾款；收款金额≠应收→400；未收齐不许完成） |

> Q-D 是**规则收紧**，不是告警：`warnings[]` 机制作废，一律 400/409 拦死。前端生成订单页「合计校验」从「只提示」改为**提交前就禁用按钮**。

---

## 附录 A：与旧方案的差异速查（给 reviewer 防串味）

| 项 | PLANNER-V2.md（作废） | 本文（定稿） |
|---|---|---|
| 商机阶段 | 8 段（lead→quoted→…→won） | 4 段：报价→待客户确认→成交/流失 |
| 商机录入 | 定金/尾款在商机里填 | 商机只填金额，押金在生成订单时填 |
| 生成订单 | 商机「赢单」即生成，无入参 | `成交` 阶段 + payload（押金/物流/运费/地址） |
| 物流方式 | `carrier` / `self` | `free` 包邮 / `agent` 代办 / `self` 自提 |
| 附件 | 仅图片、≤3 张 | 任意类型、≤10 个、单个 ≤20MB |
| 跟进方式 | 电话/微信/到面/线上 | 只有微信/电话 |
| 售后 | 3 段可「开始处理」「拒绝」 | 记跟进自动处理中；无拒绝；完成后锁定 |
| 下拉选项 | 硬编码（前后端各一份） | 12 张数据字典，A/B/C/D 分级 |
| 待跟进 | 所有历史记录 next_date ≤ 今天 | 按客户取最近一条 |
| 统计 | 4 个数字 | 8 块（KPI/趋势/漏斗/线索转化/3 个分布/来源） |

## 附录 B：本轮涉及文件清单

```
app/enums.py                 改：DEAL_STAGE / LOGISTICS_MODE / FOLLOW_METHOD / AFTERSALE_STATUS + 新增 DRIVE_TYPE/FOLLOW_KIND/ORDER_EVENT
app/dicts.py                 新增：DICT_REGISTRY + 校验 + 缓存
app/migrations.py            追加：v2_002
app/models.py                改：DealIn/DealOut/OrderIn/OrderOut/CustomerOut/Dashboard×/Stats 出参
app/services.py              改：next_no、read_files、write_timeline、create_order_from_deal、transition
app/storage.py               改：白名单扩展 + 下载头
app/routers/dicts.py         新增
app/routers/stats.py         新增
app/routers/{deals,orders,customers,carriers,followups,aftersales,dashboard,leads}.py  改
static/app.js                改：api() 真实化 + 字典驱动 + 遮罩 + 路由
static/views/*.js            覆盖：来自 static/demo/views/
static/index.html            改：导航 9 项
static/sw.js                 改：CACHE_VERSION+1
docs/PAGES-V2.md             只读（定稿依据）
docs/PLANNER-V3.md           本文
tests/test_{dicts,deal_orders,order_timeline,addresses_contacts,files,stats_workbench}.py  新增
```