# 02 · 软件架构文档

> 最后更新：2026-11-14（TASK-029 外部 Bearer Token 与新增线索）
>
> 文档状态：✅ 已建立，后续随结构、依赖、接口和数据模型变化增量维护
>
> 架构基线：`main@d2324a1`，迁移版本 `v2_023`

## 1. 架构目标

- 在既有 CRM 上增量演进，不为重构而重写。
- 单用户、低运维成本，默认单进程运行，优先保证可理解、可回滚和可恢复。
- 业务规则集中到后端服务层，前端不各自复制状态机。
- 产品主档、报价、订单使用“主数据 + 快照”，保证历史可追溯。
- SQLite 与 MySQL 保持同一业务语义，附件继续落本地磁盘。
- 页面、接口、数据库和测试均有清晰边界，便于后续继续迭代。

## 2. 系统上下文

```text
销售用户（桌面 / 手机）
        │
        ▼
浏览器 SPA：/crm/
        │ 同源请求 /crm/api/crm/*
        ▼
FastAPI 单体应用
  ├─ 认证 / 业务模块 / 统计聚合
  ├─ SQLite 或 MySQL
  ├─ 本地 uploads/
  └─ 启动迁移 / 种子数据 / 健康检查
        │
        ├─ 每日本地备份
        └─ 可选 MinIO 异地备份
```

系统外部边界：

- 客户沟通在微信或电话中完成，系统记录跟进。
- 财务确认、生产和物流执行在系统外完成，系统记录业务结果。
- 微信确认截图、Excel 下单表、PDF 和图纸通过附件上传。

## 3. 部署拓扑

### 3.1 传统部署

```text
内网 / 公网入口
      │
      ▼
nginx
  ├─ /crm/        静态文件
  └─ /crm/api/    → 127.0.0.1:8010
                         │
                         ▼
                   crm-api.service
                   uvicorn 单进程
                         │
                   data/ + uploads/
```

关键约束：

- systemd 服务显式设置 `PYTHONPATH`，避免继承错误虚拟环境。
- nginx 配置变更前先备份，语法检查通过后热加载。
- 每日备份由 `crm-backup.timer` 调度，SQLite 场景默认 03:10 执行。
- 本机内存有限，保持单进程，不引入额外中间件。

### 3.2 Docker 部署

- 同一 FastAPI 镜像可直接提供 `/crm/` 静态页和 API。
- ASGI 中间件把 `/crm/api/*` 重写到 `/api/crm/*`，兼容现有前端绝对路径。
- 数据目录和上传目录必须挂载到持久卷。
- 生产仍推荐 nginx 统一入口，并限制 CORS 和网络访问范围。

## 4. 技术栈与代码布局

| 层 | 选型 | 职责 |
| --- | --- | --- |
| API | Python + FastAPI + Pydantic | 路由、入参校验、鉴权、响应模型 |
| 前端 | 原生 JavaScript SPA | hash 路由、页面渲染、交互、无构建发布 |
| 数据访问 | SQLite / MySQL + sqlglot | 本地默认库、可选 MySQL、SQL 方言转换 |
| 文件 | 本地 `uploads/` | 跟进附件、支付截图、下单表版本 |
| Excel | openpyxl + Pillow | 下单表读取、A1 校验、金额识别、预览图片 |
| 部署 | systemd + nginx / Docker | 进程管理、静态服务、反向代理 |
| 测试 | unittest（仓库现有测试） | 接口、规则、迁移、前端结构与部署冒烟 |

目录边界：

```text
app/
  main.py             应用入口、lifespan、静态挂载
  routers/            按业务域拆分的 HTTP 接口
  services.py         跨模块业务编排、订单推进、线索转化
  models.py           Pydantic 请求/响应模型
  db.py               数据库连接与 SQLite/MySQL 适配
  migrations.py       幂等增量迁移与迁移验收
  schema.py           基础建表（SQLite）
  mysql_schema.py     MySQL 最终结构与启动种子
  db_standard.py      标准审计列、软删除触发器
  enums.py            状态码、标签和状态机
  dicts.py            数据字典注册表、缓存和校验
  storage.py          文件落盘、类型和访问校验
  quotes.py、quote_forms.py、quote_versions.py
                      报价业务、Excel 预览、版本持久化
  product_catalog.py、product_importer.py
                      产品目录、Excel 识别
  timeline.py         对象履历写入
  lead_tags.py、deal_tags.py
                      线索/商机标签
static/
  index.html          页面壳与全局版本号
  app.js              路由、鉴权、全局状态
  views/              每页一个业务视图
  demo/               设计对照，不作为生产 API
  sw.js、manifest.json
                      离线壳和 PWA
tests/                自动化回归
ops/                  部署、备份和运维脚本
docs/                 产品、架构、进度及专题文档
```

## 5. 逻辑分层

```text
浏览器视图
  static/views/*.js
        │
        ▼
HTTP 边界
  app/routers/*.py + app/models.py
        │
        ▼
业务编排
  app/services.py、quotes.py、timeline.py、dicts.py、
  product_*.py、tag *.py
        │
        ▼
持久化与文件
  app/db.py、schema.py、migrations.py、
  mysql_schema.py、storage.py
```

分层规则：

1. 路由负责鉴权、参数解析和响应组装，不直接实现复杂跨表业务。
2. 状态推进、金额校验、快照复制、标签同步和履历写入由服务层统一处理。
3. 前端只消费后端状态和标签，不维护另一套状态机。
4. 所有文件下载都经过附件接口，不直接暴露上传目录。
5. 数据字典是业务选项的唯一来源；状态机值域仍由代码注册表约束。

## 6. 核心模块边界

| 模块 | 主要文件 | 责任 | 不承担 |
| --- | --- | --- | --- |
| 认证 | `routers/auth.py`、`security.py` | 登录、会话、改密码、显示名 | 多角色权限 |
| 外部 API | `routers/external_leads.py`、`external_auth.py` | Bearer Token 鉴权、外部新增线索 | Cookie 回退、Token 管理界面 |
| 线索 | `routers/leads.py`、`lead_tags.py` | 线索 CRUD、状态、转化检查、标签 | 客户 360 |
| 导入 | `routers/csvimport.py` | 模板、字段映射、预览、整批导入线索 | Excel 直接导入、客户导入 |
| 客户 | `routers/customers.py`、`addresses.py` | 客户、联系人、地址簿、360 查询 | 脱离线索的常规新建 |
| 产品 | `routers/products.py`、`product_*` | 产品主档、下单表、识别 | 具体客户报价 |
| 商机 | `routers/deals.py` | 商机、产品工作清单、标签、阶段派生、生成订单后归档只读 | Excel 报价明细 |
| 报价 | `routers/quotes.py`、`quote_*` | 报价单、明细、发送、确认、作废、下单 | 订单收款 |
| 订单 | `routers/orders.py`、`services.transition()` | 订单快照、金额、状态、物流、时间线 | 售后处理正文 |
| 售后 | `routers/aftersales.py` | 售后单、状态和 SLA 数据 | 改回订单状态 |
| 物流 | `routers/carriers.py` | 物流公司、多联系人、停用保护 | 实际承运轨迹 |
| 统一跟进 | `routers/followups.py`、`timeline.py` | 五类对象跟进、附件、常用短语、履历 | 业务状态机主体 |
| 工作台 | `routers/dashboard.py` | 待办和经营聚合 | 明细数据编辑 |
| 统计 | `routers/stats.py` | KPI、趋势、漏斗和分布 | 修改业务数据 |
| 字典 | `routers/dicts.py`、`dicts.py` | 12 类字典、分级维护、型号检索 | 任意状态机扩展 |

## 7. API 约定

- 页面 API 统一前缀：`/api/crm`。
- 外部 API 统一前缀：`/api/external/v1`。
- 反向代理地址：`/crm/api/crm/*`。
- 鉴权：页面 API 使用 Cookie `crm_sid`；外部 API 只使用 `Authorization: Bearer <token>`，两种凭据不能互相替代。
- 响应：JSON；写接口使用明确的 HTTP 状态码和业务错误码。
- 分页：列表接口按业务需要返回 `items`、`total`、`page`、`size` 或直接数组。
- 日期：业务日期使用本地日期 `YYYY-MM-DD`；审计时间使用 ISO 时间。
- 金额：数值型字段，服务端统一 `round(value, 2)` 后校验。

主要端点和页面：

| 页面 | 路由 | 主要端点 |
| --- | --- | --- |
| 工作台 | `#/dashboard` | `GET /dashboard` |
| 线索 | `#/leads`、`#/leads/{id}/follow` | `/leads`、`/follow-ups` |
| 客户 | `#/customers`、`#/customers/{id}` | `GET/PUT /customers`、`GET /customers/{id}/360`、`/addresses`；`POST /customers` 固定拒绝 |
| 产品 | `#/products`、`#/products/{id}` | `/products`、`/products/{id}/form-file` |
| 商机 | `#/deals`、`#/deals/{id}` | `/deals`、`/deals/{id}/quotes`、`/deals/{id}/tags` |
| 报价 | 商机详情内 | `/quotes/{id}/send|requote|void|confirm|orders`、`/quotes/{id}/shipping-recipient` |
| 订单 | `#/orders`、`#/orders/{id}` | `/orders`、`/orders/{id}/payment`、`/transition` |
| 售后 | `#/aftersales`、`#/aftersales/{id}` | `/aftersales`、`/aftersales/{id}/finish` |
| 物流 | `#/logistics` | `/carriers` |
| 统计 | `#/stats` | `GET /stats?months=6` |
| 字典 | `#/dict`、`#/dict/{code}` | `/dicts`、`/dicts/{code}/items` |

## 8. 数据模型

### 8.1 表清单

MySQL 基线共 29 张表，按业务域分组如下：

| 域 | 表 |
| --- | --- |
| 身份 | `users`、`sessions`、`api_tokens` |
| 线索 | `leads`、`lead_tags` |
| 客户 | `customers`、`customer_addresses` |
| 产品 | `products` |
| 商机与报价 | `deals`、`deal_items`、`deal_tags`、`deal_quotes`、`quote_items` |
| 订单 | `orders`、`order_items`、`order_status_log` |
| 售后 | `aftersales`、`aftersale_status_log` |
| 物流 | `carriers`、`carrier_contacts` |
| 跟进与文件 | `follow_ups`、`attachments`、`follow_up_phrases` |
| 标签与导入 | `tags`、`customer_tags`、`import_log` |
| 字典与迁移 | `dict_items`、`schema_migrations`、`migration_clear_guard` |

### 8.2 关系

关系由应用代码维护，不依赖数据库外键：

```text
lead ──转换──▶ customer ──1:N──▶ deal ──1:N──▶ quote
                                   │              │
                                   └──── N:1 ─────┘
                                                  │
                                                  ▼
                                               order
                                                  │
                              ┌───────────────────┼───────────────┐
                              ▼                   ▼               ▼
                         order_items       order_status_log    aftersales
                                                                  │
                                                           aftersale_status_log
```

通用关联：

- `follow_ups(object_type, object_id)` 挂五类业务对象。
- `attachments(object_type, object_id)` 挂跟进、支付截图或售后凭证。
- `customer_addresses` 关联客户。
- 公司客户的 `customers.name` 保存公司名，`customers.company_name` 保存主联系人姓名；联系电话和微信保存在同一客户主档。
- `carrier_contacts` 关联物流公司。
- `api_tokens.user_id` 关联绑定用户；Token 校验要求用户未停用、未删除。
- `leads.created_by` 保存页面或外部创建时的责任用户 ID；历史行为空。
- `deal_quotes` 和 `quote_items` 保存报价时点的产品、价格和 Excel 版本。
- `orders.order_name` 保存从客户已确认报价单继承的订单名称快照，后续可在订单编辑中修改。
- `order_items` 保存生成订单时的产品快照。
- 订单表单读取 `customer_addresses` 作为历史收件人及地址来源；订单仍保存独立收货快照。

### 8.3 标准字段与删除策略

每条表必须保留或自动补齐：

| 字段 | 含义 |
| --- | --- |
| `create_time` | 标准创建时间 |
| `update_time` | 标准最后更新时间 |
| `is_delete` | 0 有效，1 已软删除 |

为兼容旧接口，部分表同时保留 `created_at` / `updated_at`。标准时间列由触发器维护，业务接口继续返回既有字段。

删除策略：

- 普通业务记录优先软删除。
- 已被订单引用的报价单、物流公司和关键主数据不得物理删除。
- 附件数据库行软删除；物理文件清理必须经过独立、可备份的运维流程。

## 9. 状态模型

### 9.1 线索

```text
new 新线索 → following 跟进中 → converted 已转化
                    └────────→ invalid 已失效
```

### 9.2 报价单

```text
draft 报价 ⇄ pending 待客户确认 → confirmed 客户已确认
     └────────────────────────→ void 历史
```

限制：

- 仅 `draft` 可完整编辑。
- `pending` 可退回 `draft` 重新报价。
- `confirmed` 不可作废、删除或退回。
- 任一报价单进入 `confirmed` 时，同一商机其他报价单在同一事务内转为 `void`；`void` 对外显示“历史”，只读且不能关联新跟进。
- 同一商机最多一张 `confirmed`。
- 报价列表按 `confirmed → pending → draft → void` 分组，同组按 `updated_at DESC, id DESC` 排序。

### 9.3 商机阶段

活跃阶段：

```text
quote 报价 → confirm 待客户确认 → won 客户已确认
   └────────────────────────────→ lost 作废
```

当前报价单流程下，商机阶段由报价单状态派生：

- 存在客户已确认报价单 → `won`
- 存在待客户确认报价单 → `confirm`
- 存在报价草稿 → `quote`
- 所有报价单均作废 → `lost`

商机存在 `order_id` 时，对外状态统一显示“已生成订单”，整条商机进入归档只读：基本信息、备注、产品、报价和已有标签均不可修改，页面隐藏不可执行的操作按钮。

### 9.4 订单

```text
pending_payment 待支付
  → deposit_paid 已支付定金
  → producing 生产中
  → balance_paid 已支付尾款
  → ready_to_ship 待发货
  → completed 已完成
```

兼容说明：

- `pending_confirmation` 为早期多产品订单流程保留值，当前报价单客户确认流程不会新造该状态。
- 不再提供 `shipped` 活跃状态；从 `ready_to_ship` 确认发货时直接写入 `completed`，并在同一事务内保存物流、运单号、发货时间和完成时间。
- `shipped` 仅可能出现在取消状态前的状态日志中，标签映射保留“已发货”用于历史显示；存量订单由 `v2_022` 自动迁移为 `completed`。
- 状态推进使用 `ORDER_FLOW`，只允许下一状态；若确认发货新增运费导致更新后的订单应收超过已收金额，则在写库前拒绝完成。

### 9.5 售后

```text
pending 待处理 → processing 处理中 → done 已完成
```

- 添加第一条跟进后自动进入 `processing`。
- `done` 后不可继续跟进或改状态。
- `rejected` 仅作为历史数据可读值，不再可写。

## 10. 关键数据流

### 10.1 线索转客户和商机

1. 路由校验线索状态、联系方式和商机参数。
2. `services.convert_lead()` 在一个事务内建立或关联客户。
3. 迁移联系人、标签、意向、历史跟进和创建时间。
4. 创建首个商机并写系统履历。
5. 线索更新为 `converted`，提交后所有页面读取同一关系。

客户手机号在这一事务中从线索复制，之后作为稳定身份锚点保持只读。客户路由不接受直接建档，CSV 导入固定写线索池；这两个旁路分别返回稳定业务错误，不产生业务行。手机号更新在读取记录和写入字段前拒绝，因此即使提交值与原值相同，也不能借机修改同请求中的其他字段。

### 10.2 报价单

1. 商机详情创建报价单，状态初始为 `draft`。
2. 选择产品主档并上传该产品对应的本次 `.xlsx` 下单表。
3. `quote_forms` 读取 `Sheet1`、校验 `A1`、识别合计并生成样式预览。
4. 报价产品保存最终金额、识别金额、文件版本和产品快照。
5. 发送后状态进入 `pending`；客户确认后进入 `confirmed`，同一事务内将其他报价单转为历史，并同步商机阶段和自动标签。

### 10.3 报价单生成订单

1. 校验报价单已 `confirmed` 且尚未生成订单。
2. 生成订单表单可调用 `GET /quotes/{id}/shipping-recipient`：服务端优先读取报价明细已持久化的 `form_content_json`，再从 `Sheet1!A2`（兼容 `A1`）和 `Sheet1!B3` 提取收货人、电话和地址；旧数据缺少内容快照时回读该版本 Excel。
3. 多张产品下单表必须给出一致的收货信息，否则拒绝自动覆盖并提示人工填写。
4. 复制报价明细、产品快照和下单表引用到订单。
5. 将客户已确认报价单标题复制到 `orders.order_name`。
6. 计算产品合计、优惠、产品应收、运费和订单应收。
7. 校验定金及尾款恒等式，保存物流和收货快照。
8. 商机归档为“已生成订单”，订单复制产品、价格、参数和下单表快照，写报价、订单和状态履历。

### 10.4 订单推进

1. `services.transition()` 校验当前状态、目标状态和收款金额。
2. 同一事务更新订单、写状态日志、必要时写附件和统一履历。
3. 失败时整体回滚，不允许出现状态变了但日志或金额没写。
4. 订单完成后才允许建立售后。

### 10.5 外部新增线索

1. `external_auth.require_external_token()` 只解析 Bearer 请求头，并校验 Token 未删除、未撤销、未过期且绑定用户启用。
2. 外部请求只允许业务字段；来源固定 `api`、状态固定 `new`、默认类型 `other`，Token 绑定用户写入 `created_by`。
3. 手机号使用 `app/phone.py` 规范为大陆手机号；有效线索或客户冲突返回 409 摘要。
4. `app/lead_service.py` 统一完成重复检查、线索插入、标签关联和创建履历，页面和外部接口共用同一写入路径。
5. 外部路由返回 201；失败请求不写线索或标签。

## 11. 数据字典机制

- 注册表定义：`app/dicts.py::DICT_REGISTRY`。
- 数据表：`dict_items`。
- 级别：A 可增删改停用，B 只改名排序，C 只改名，D 只读。
- 被引用项不能删除，只能停用。
- 字典值使用稳定的英文 key，显示名来自 label。
- 写操作清空进程内标签缓存；单进程部署下即时生效。
- 前端通过 `/dicts` 加载并缓存，表单和列表共用同一份选项。

## 12. 文件与安全

### 12.1 上传

- 存储键格式为 `YYYY/MM/DD/<uuid>.<ext>`。
- 文件名经过清洗，存储路径不能由客户端任意指定。
- 单条跟进最多 10 个附件，单文件最大 20MB。
- 附件白名单覆盖图片、PDF、Excel、Word、DWG/DXF 和 ZIP。
- 扩展名和 MIME/文件签名双层校验；HTML、SVG、JS 等可执行页面类型拒绝。
- 保存失败或事务回滚不得产生可见业务记录。

### 12.2 下载

- 默认 `Content-Disposition: attachment`。
- 图片预览必须使用显式 `inline=1`。
- 统一返回 `X-Content-Type-Options: nosniff`。
- 读取存储键前校验路径越界，缺失文件返回 404。

### 12.3 认证

- 密码使用 PBKDF2 哈希入库。
- 会话使用不可预测 token，Cookie 设置 `HttpOnly` 和 `SameSite=Lax`。
- 会话有效期固定 12 小时。
- 生产使用 HTTPS 时启用 `Secure` Cookie。

## 13. 数据库与迁移

### 13.1 SQLite / MySQL 兼容

- 默认 SQLite 适合单用户、本地和轻量部署。
- MySQL 使用 `utf8mb4`，表结构由 `mysql_schema.py` 定义。
- `db.py` 负责少量 SQLite 方言到 MySQL 的转换，包括时间函数、`INSERT OR IGNORE`、`last_insert_rowid` 等。
- 业务层尽量使用参数化查询；数据库特有 SQL 必须有兼容测试。

### 13.2 迁移

- 当前迁移版本：`v2_023`。
- 启动时幂等执行基础建表、增量迁移、标准审计列补齐和种子数据。
- 每条迁移有版本或结构 guard，可重复执行。
- 迁移失败必须停止启动，不得带半迁移状态对外服务。
- 迁移前后对关键业务表做行数保护。
- 存量数据升级前先备份。

### 13.3 硬约束

项目数据库规则：

- 每张表必须有 `create_time`、`update_time`、`is_delete`。
- 表字段不允许有外键，关联完整性由应用事务保证。

架构现状：

- MySQL 物理 DDL 已符合无外键和标准字段要求。
- SQLite 的部分历史建表语句仍带有 `REFERENCES` 声明。这些声明是遗留 DDL，后续迁移应逐步清理；新增表和物理设计不得再引入外键。

## 14. 聚合与查询口径

### 14.1 待跟进

- 每个业务对象只取最近一条 `kind='follow'` 的跟进。
- `next_date` 为空不提醒。
- `next_date <= 今天` 进入待办；小于今天为逾期。
- 已确认或已作废商机关联的提醒退出普通待办。
- 同一客户新记一条较晚跟进后，旧记录不再占据待办。

### 14.2 统计

- “本月”按亚洲/上海自然月。
- 金额统一汇总到两位小数。
- 商机漏斗采用累计到达口径。
- 产品型号只是初值，实际尺寸使用商机或订单保存的 `spec`。
- 完成成交和销售额只认已确认或已完成业务状态，不把报价草稿计入成交。

### 14.3 工作台售后概览

- “进行中售后”使用独立计数，口径固定为状态 `pending` 或 `processing`。
- `active_aftersales_count` 返回全部未完成售后数量，不受提醒列表展示条数限制。
- `recent_aftersales` 最多返回最近 4 张未完成售后单；已完成和已拒绝记录均排除。
- 今日待跟进的人工跟进入口按关联业务对象跳转：有 `deal_id` 时进入商机详情，否则进入客户详情。

### 14.4 搜索

- 用户输入先去除前后空格。
- 参数化查询防止 SQL 注入。
- `%`、`_`、`\` 按普通字符处理，避免模糊搜索退化为全表匹配。

## 15. 前端架构

- 单页应用，hash 路由，避免 nginx 需要为每个路径配置回退。
- `app.js` 负责登录、会话、导航、全局状态、字典加载和路由分发。
- `views/*.js` 按页面拆分；公共表格、弹窗、跟进时间线、金额格式化放在 `shared.js`。
- 页面级样式与共享样式分开，避免修改某页影响全站。
- 图片查看器当前页弹出，不新开浏览器标签。
- 金额遮罩只影响显示，不改变 API 数据。
- 前端版本号与 Service Worker 缓存版本必须一起更新。

## 16. 测试与验证架构

测试分四层：

| 层级 | 目标 | 代表文件 |
| --- | --- | --- |
| 规则/接口 | 状态、金额、权限、事务 | `test_deal_quotes.py`、`test_orders.py`、`test_aftersales.py` |
| 迁移/数据库 | 幂等、字段、行数、SQLite/MySQL 兼容 | `test_migrations.py`、`test_database_compatibility.py` |
| 前端结构 | 路由、表单、交互入口和缓存版本 | `test_*_ui.py`、`test_form_layout.py` |
| 部署 | Docker 配置、健康检查 | `test_docker_deployment.py`、`test_health.py` |

测试保护规则：

- 必须使用隔离数据库和隔离上传目录。
- 严禁让 `CRM_DB` 指向生产库。
- 失败断言不能用删测试的方式消除；修改口径时同步修改断言和需求。
- 后端代码改动后重启服务并做健康检查；本对话只改文档，不需要重启后端。

## 17. 架构决策记录

### ADR-001 · 增量演进

- 背景：已有 V1 登录、部署、备份、上传可用，业务表可清空后重建。
- 决策：保留基础设施和单用户模型，通过迁移增加业务能力。
- 取舍：降低上线风险，但需要维护兼容字段和迁移链。

### ADR-002 · FastAPI 单体 + 原生 SPA

- 背景：单用户、内网、低资源，团队规模小。
- 决策：使用单体 FastAPI 和无构建原生 JS。
- 取舍：部署简单，不引入 Node 构建链；前端工程化能力有限。

### ADR-003 · SQLite 默认，MySQL 可选

- 背景：单用户场景 SQLite 足够，但已有 MySQL 迁移需求。
- 决策：保持双数据库兼容。
- 取舍：增加 SQL 方言和迁移测试成本。

### ADR-004 · 产品主档 + 快照

- 背景：产品可改名或替换 Excel，但历史报价必须可追溯。
- 决策：主档保存当前配置，商机和订单保存关键字段与文件版本快照。
- 取舍：存在受控冗余，换取历史稳定性。

### ADR-005 · 以报价单确认作为下单闸门

- 背景：多方案、多产品和 Excel 下单表需要客户明确确认。
- 决策：只有客户已确认报价单可生成订单，且一个商机最多一张确认单。
- 取舍：流程比直接商机下单多一步，但显著减少错单。

### ADR-006 · 统一跟进与履历

- 背景：线索、客户、商机、订单、售后都需要沟通记录。
- 决策：共用 `follow_ups`，人工跟进和系统事件通过 `kind` 区分。
- 取舍：查询需按对象过滤，但前端可复用时间线。

### ADR-007 · 受控数据字典

- 背景：纯硬编码导致前后端选项漂移，纯自由编辑会破坏状态机。
- 决策：A/B/C/D 分级，值域仍由代码注册表约束。
- 取舍：业务可维护性提升，但新增状态仍需开发参与。

### ADR-008 · 无数据库外键

- 背景：项目数据库规范要求不使用外键，便于跨库和迁移。
- 决策：只保存关联 ID，删除限制、级联逻辑和关系校验放应用层。
- 取舍：应用必须承担完整性责任，测试需覆盖孤立和误删场景。

### ADR-009 · 文件本地保存并受控下载

- 背景：附件是业务证据，单机部署和备份流程简单。
- 决策：附件存本地目录，数据库保存元数据；下载接口统一安全头。
- 取舍：无法直接多机共享，扩展时必须先设计对象存储迁移。

### ADR-010 · 商机阶段由报价单派生

- 背景：旧阶段与报价单状态重复且容易漂移。
- 决策：在报价流程中根据报价单状态同步商机阶段。
- 取舍：商机不能脱离报价单任意推进，更符合当前业务。

### ADR-011 · 生成订单后的商机归档

- 背景：订单已经复制产品、价格和下单表快照，继续修改商机会造成来源数据与订单事实不一致。
- 决策：以 `deals.order_id` 是否存在作为归档判定；生成订单后商机及标签全部只读，前端只渲染查看型入口。
- 取舍：备注和沟通不再回写商机，统一记录到订单或售后，换取成交来源的稳定与可追溯。

### ADR-012 · 订单名称采用独立快照

- 背景：客户已确认报价单的名称适合作为订单默认名称，但订单后续可能按交付或客户习惯调整名称；订单编号必须保持系统生成的稳定标识。
- 决策：新增 `orders.order_name`，生成订单时从来源报价单标题复制；订单编辑接口允许修改名称并记录履历，订单编号保持只读。
- 取舍：订单名称与报价单标题可能不同，但订单仍保留 `quote_id`，可追溯来源报价单。

### ADR-013 · 确认发货后直接完成订单

- 背景：用户确认发货已代表交付动作完成，单独保留“已发货”状态增加了无业务意义的二次点击。
- 决策：取消 `shipped` 活跃状态，`ready_to_ship` 的下一状态直接为 `completed`；确认发货时原子写入物流信息、运单号、发货时间和完成时间。
- 存量兼容：`v2_022` 将 `orders.status='shipped'` 收敛为 `completed`，新增一条自动完成日志，并软删除订单状态字典中的 `shipped` 项；原历史日志不重写。
- 取舍：历史状态日志仍可能出现 `shipped`，因此保留只读兼容标签；新业务不能再进入或筛选该状态。

### ADR-014 · 客户只由线索转化产生且手机号不可变

- 背景：直接建客户、CSV 导入客户和编辑客户手机号会让客户缺少来源线索，或让客户与来源线索的手机号不一致，破坏后续按手机号匹配、跟进和去重。
- 决策：客户仅由线索转化事务创建；CSV 固定导入线索；客户手机号继承来源线索且转客后不可修改。记录见 `docs/adr/0001-customer-origin-invariant.md`。
- 取舍：历史无来源客户或手机号不一致数据不会被自动修补，而由后续上线审计报告交人工处理。

### ADR-015 · 外部 API Token 明文保存且不限制来源 IP

- 背景：外部服务端集成不能依赖浏览器 Cookie；项目明确要求 Token 长期保存在数据库中，并允许集成服务器迁移。
- 决策：`api_tokens.token` 保存完整 Token，支持多行、可选过期、撤销和用户绑定；请求只接受 Bearer 头，不增加 IP 白名单。
- 取舍：数据库读取权限等同凭据读取权限，必须通过备份、账号和日志管理降低泄露风险；泄露后用 `revoked_at` 撤销。详见 `docs/adr/0002-plaintext-api-token-no-ip-allowlist.md`。

## 18. 架构约束与已知债务

| 项 | 当前状态 | 约束或后续方向 |
| --- | --- | --- |
| 单进程 | 当前基线 | 状态缓存、字典缓存按单进程设计 |
| CORS | Docker 调试允许跨源 | 生产入口应收窄来源，优先同源 nginx |
| SQLite 遗留外键声明 | 部分旧 DDL 仍存在 | 后续迁移清理，新增结构不得引入 |
| 自动化 UI 测试 | 以结构和源码断言为主 | 关键发布仍需浏览器冒烟 |
| MySQL | 有兼容测试和迁移手册 | 实机写链路需在具备 MySQL 的环境验证 |
| 旧专题文档 | 内容多且存在时间差 | 冲突以三份主文档为准，逐步收敛 |

## 19. 架构变更规则

发生以下变化时必须更新本文：

- 新增或删除模块、依赖、服务或外部系统。
- 新增/删除表、关键字段、索引或迁移版本。
- 修改状态机、核心金额公式、权限模型或文件安全策略。
- API 前缀、认证方式、部署拓扑发生变化。
- 做出非显然技术选择，且未来维护者可能重新讨论。

变更时在对应章节追加内容，并在 `03-progress.md` 记录任务和影响。
