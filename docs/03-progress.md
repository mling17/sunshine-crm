# 03 · 项目进度

> 最后更新：2026-11-19
>
> 当前代码基线：`main@d2324a1`
>
> 当前迁移版本：`v2_025`
>
> 当前阶段：核心业务已形成闭环；外部 API 已完成 Token 鉴权、新增线索、新增跟进、批量手机号校验和幂等重试。

## 1. 当前状态概览

| 领域 | 状态 | 说明 |
| --- | --- | --- |
| 登录与会话 | ✅ 已完成 | 单用户登录、12 小时会话、改密码、显示名 |
| 线索管理 | ✅ 已完成 | 新建、编辑、搜索、标签、跟进、失效、CSV 导入 |
| 外部 API | ✅ 已完成 | Token、新增线索、按手机号新增跟进、手机号批量校验和写接口幂等重试 |
| 线索转化 | ✅ 已完成 | 自动建客户和商机，支持关联已有客户 |
| 客户管理 | ✅ 已完成 | 客户 360、联系人、地址簿、画像、渐进履历；只允许线索转化产生，手机号不可变 |
| 产品主档 | ✅ 已完成 | 123 个初始产品与独立 Excel 下单表 |
| 商机与报价 | ✅ 已完成 | 多报价单、多产品、版本化 Excel；确认后其他报价转历史，出单后归档只读 |
| 订单 | ✅ 已完成 | 订单名称、快照、金额拆分、收款、物流、状态履历、历史收货地址、报价单收货信息提取 |
| 售后 | ✅ 已完成 | 完成订单发起、多售后、SLA、完成锁定 |
| 统一跟进 | ✅ 已完成 | 五类对象、任意附件、常用短语、系统履历 |
| 工作台与统计 | ✅ 已完成 | 今日工作、销售/订单聚合、图表口径 |
| 数据字典 | ✅ 已完成 | 12 类字典、A/B/C/D 分级维护 |
| SQLite | ✅ 已完成 | 默认运行库、迁移、备份恢复 |
| MySQL | 🚧 部分验证 | 结构、方言与迁移工具已具备；本次未连接真实 MySQL |
| Docker | ✅ 已完成 | 单镜像可同时提供前端和 API |
| 自动化回归 | ✅ 已完成 | 2026-11-14 本次隔离回归 553 通过、2 跳过 |
| 生产发布 | 📋 待执行 | 上线脚本与验证包已完成；尚未连接生产库或真实 MySQL 执行 |

## 2. 当前任务

| 任务 | 内容 | 状态 | 验收 |
| --- | --- | --- | --- |
| TASK-018 | 补齐 `01-prd.md`、`02-arch.md`、`03-progress.md`，建立三份文档的单一事实来源 | ✅ 已完成 | 文档存在、口径一致、变更日志已记录 |
| TASK-019 | 选定一个具备真实 MySQL 8 的环境执行写入、备份和恢复演练 | 📋 待办 | 迁移行数一致，健康检查和写链路通过 |
| TASK-020 | 在发布前用移动端和桌面端完成真实数据冒烟 | 📋 待办 | 核心链路、附件、字典、统计和回滚检查通过 |
| TASK-021 | 商机生成订单后进入归档只读状态，隐藏不可执行按钮 | ✅ 已完成 | 后端写接口全部拒绝，标签和商机数据保持不变，前端只保留查看入口 |
| TASK-022 | 工作台今日待跟进、已逾期数字卡改为同页滚动定位 | ✅ 已完成 | 两张卡均滚动到当前页今日待跟进区域，不再进入独立表单 |
| TASK-023 | 工作台跟进入口跳详情，售后概览仅保留未完成单 | ✅ 已完成 | 跟进进入关联商机/客户详情，进行中售后数量与提醒口径一致 |
| TASK-024 | 订单名称继承报价单，表单复用客户历史收件地址，详情主标题显示名称 | ✅ 已完成 | 名称可修改、编号不可修改，生成和编辑表单均可选历史地址 |
| TASK-025 | 报价单按确认优先级排序，客户确认后其他报价转历史，确认后仅保留生成订单入口 | ✅ 已完成 | 历史报价只读；商机出单后仍整体快照锁定 |
| TASK-026 | 生成订单表单从报价单 Sheet1 提取收货人、电话和地址 | ✅ 已完成 | A2（兼容 A1）和 B3 可正确填入，缺失或冲突时提示人工填写 |
| TASK-027 | 取消“已发货”订单状态，确认发货后直接完成订单 | ✅ 已完成 | 状态字典和状态机移除 shipped；确认发货原子写入物流与完成时间；历史 shipped 自动完成 |
| TASK-028 | 客户只能由线索转化产生，CSV 只导线索，客户手机号不可变 | ✅ 已完成 | 直接建档、客户导入和手机号更新均返回稳定错误且不写数据；转化仍原子迁移标签和跟进 |
| TASK-029 | 外部 Bearer Token 鉴权与新增线索 | ✅ 已完成 | Token 生命周期校验一致返回 401；外部手机号规范化、API 来源、重复摘要和创建人审计通过 |
| TASK-030 | 外部按手机号新增跟进与多附件 | ✅ 已完成 | 客户优先/线索回退、稳定匹配错误、10 附件上限、页面/外部共享原子写入和创建人审计通过 |
| TASK-031 | 外部批量校验线索手机号 | ✅ 已完成 | 1/500 边界、整批非法位置、规范化去重、线索生命周期过滤和隐私响应通过 |
| TASK-032 | 外部写接口幂等重试 | ✅ 已完成 | 相同请求回放响应；内容变化返回冲突；Token/端点隔离；附件与业务写入不重复 |
| TASK-033 | 外部 API 生产更新脚本、审计与上线验证包 | ✅ 已完成 | `v2_022 -> v2_025` SQLite/MySQL 脚本收敛；preflight/postcheck、Token 模板、上线手册和第三方 API 文档齐备 |
| TASK-034 | 代码审查整改：外部手机号错误契约与共享校验 | ✅ 已完成 | 非字符串批次项返回 `invalid_phone` 和位置；跟进对象校验、手机号比较键和外部 Token 测试夹具复用 |
| TASK-035 | 共享列表外壳与线索分页/排序（Ticket #9） | ✅ 已完成 | size 白名单 10/20/50/100/500、sort 白名单服务端 SQL 映射均 400 兜底；线索表头三态排序、页码按钮、每页条数；状态写 `#/leads` hash URL，改排序或条数回第 1 页 |
| TASK-037 | 商机列表服务端分页与排序（Ticket #13） | ✅ 已完成 | `GET /deals` 改 `{items,total,page,size}`，复用线索/客户白名单口径（8 个可排序列，尺寸=`spec`），默认 `updated_at DESC, id DESC`；商机页接入共享外壳，stage 页签与分页排序同写 hash URL |
| TASK-038 | 产品列表服务端分页、排序与筛选（Ticket #14） | ✅ 已完成 | `GET /products` 改 `{items,total,page,size}`，复用线索/客户/商机白名单口径（`product`/`drive_type`/`status` 可排序，`drive_type` NULL 沉底），默认天窗分类优先 → `series` → `code` → `id DESC`；五个筛选条件服务端执行；产品页接入共享外壳，筛选 + 分页排序状态同写 `#/products` hash URL |
| TASK-036 | 客户列表接入共享外壳与上次跟进列（Ticket #10） | ✅ 已完成 | 客户列表复用同一套分页/排序白名单（含 `name` 列），新增派生 `last_follow`（仅人工跟进）；六个可排序列表头 + 上次跟进列；状态写 `#/customers` hash URL，筛选/排序/条数变更回第 1 页；本地 pagerHtml 已移除 |
| TASK-039 | 售后列表服务端排序与共享外壳（Ticket #11） | ✅ 已完成 | `GET /aftersales` 复用共享 size 白名单（10/20/50/100/500），新增 `sort/order`（`aftersale_no`/`type`/`order`/`customer`/`problem`/`status`/`created_at`，JOIN 列只走服务端白名单 SQL）；`problem` 可空双向 NULL 沉底；默认 `created_at DESC, id DESC`；状态/订单/客户筛选与排序共存；售后页接入共享外壳，三态页签 + 分页排序同写 `#/aftersales` hash URL |
| TASK-040 | 订单列表服务端分页与排序（Ticket #12） | ✅ 已完成 | `GET /orders` 改 `{items,total,page,size}`，复用共享白名单口径（7 个可排序列，客户名走 JOIN，可空列双向 NULL 沉底），默认 `id DESC`；订单页接入共享外壳，状态页签与分页排序同写 `#/orders` hash URL，本地未定义的 `pagerHtml` 调用移除 |
| TASK-041 | 物流公司列表服务端分页、排序与筛选（Ticket #15） | ✅ 已完成 | `GET /carriers` 改 `{items,total,page,size}`，复用共享白名单口径（`name`/`address` 可排序，`address` NULL 沉底），默认被订单关联次数倒序 → `id DESC`；仅看启用、关键词筛选服务端执行；物流页接入共享外壳，筛选 + 分页排序同写 `#/logistics` hash URL；顺带修复 `is_active` 更新从未落库 |
| TASK-042 | 跟进历史页去除表单并接入分页排序（Ticket #16） | ✅ 已完成 | `GET /follow-ups` 改 `{items,total,page,size}`，复用共享白名单口径（`customer`/`deal_stage`/`content`/`next_date`/`created_at` 可排序，JOIN 列只走服务端 SQL 映射，可空列 NULL 沉底），默认 `created_at DESC, id DESC`；历史页去掉「记一条跟进」表单，改纯跟进流水表格并接入共享外壳，筛选 + 分页排序同写 `#/followups` hash URL；详情页履历调用适配新契约 |
| TASK-043 | 列表外壳推广代码审查整改（shared.js 缓存、商机出单物流下拉） | ✅ 已完成 | 删除 deals.js 遗留 carrierList 行，shared.js/deals.js 缓存版本刷新，前端结构测试锁定 |

## 3. 已完成任务

| 任务 | 内容 | 状态 | 结果 |
| --- | --- | --- | --- |
| TASK-001 | V1 登录、基础客户/商机、上传、部署和备份 | ✅ 已完成 | 2026-10-29 上线并通过 87 条基线测试 |
| TASK-002 | V2 增量迁移：线索、订单、售后、物流、统一跟进 | ✅ 已完成 | 迁移版本门控和备份机制生效 |
| TASK-003 | 线索池、转化、标签、CSV 导入 | ✅ 已完成 | 线索到客户/商机链路闭环 |
| TASK-004 | 客户 360、多联系人、地址簿和客户画像 | ✅ 已完成 | 一页汇总档案、商机、订单、售后和履历 |
| TASK-005 | 数据字典及 A/B/C/D 分级 | ✅ 已完成 | 业务选项可由页面维护，状态机仍受代码约束 |
| TASK-006 | 订单状态、收款、物流与时间线 | ✅ 已完成 | 七态推进、金额和事务校验 |
| TASK-007 | 售后三态、3 天 SLA、完成锁定 | ✅ 已完成 | 记跟进自动转处理中，终态只读 |
| TASK-008 | 工作台与统计工作台 | ✅ 已完成 | 今日工作、销售漏斗、订单和售后聚合 |
| TASK-009 | 产品主档与 123 份 Excel 下单表 | ✅ 已完成 | 产品编码、模板存储、识别和快照 |
| TASK-010 | 报价单 V1 | ✅ 已完成 | 多报价、Excel A1 校验、金额识别、预览图 |
| TASK-011 | 多产品报价与订单金额拆分 | ✅ 已完成 | 优惠与运费分离，确认后生单 |
| TASK-012 | 报价单版本、重新报价、作废和自动标签 | ✅ 已完成 | 历史 Excel 下载版本保持独立 |
| TASK-013 | 订单详情、编辑、物流联系人和售后关联 | ✅ 已完成 | 已完成订单锁定，售后可关联同订单历史 |
| TASK-014 | 跟进常用短语、批量选文件、“下次跟进”开关 | ✅ 已完成 | 五类对象均可使用 |
| TASK-015 | 地区检索、线索字段和列表布局优化 | ✅ 已完成 | 长文本截断，表单保持紧凑双列 |
| TASK-016 | MySQL 兼容、迁移与备份恢复文档 | ✅ 已完成 | 兼容测试通过；真实库演练单列待办 |
| TASK-017 | Docker 单服务打包与静态/API 同源访问 | ✅ 已完成 | 支持持久化数据与上传目录 |
| TASK-021 | 已生成订单商机归档只读 | ✅ 已完成 | 备注、标签及关联写接口锁定，页面移除不可执行按钮 |
| TASK-022 | 工作台待跟进数字卡同页导航 | ✅ 已完成 | 卡片滚动定位、焦点管理和减少动态效果已覆盖 |
| TASK-023 | 工作台跟进详情与未完成售后概览 | ✅ 已完成 | 移除快捷跟进弹窗，新增未完成售后准确计数与未完成提醒 |
| TASK-024 | 订单名称与历史收件地址 | ✅ 已完成 | `v2_020` 新增长期订单名称字段；历史地址填充与只读编号已接入 |
| TASK-025 | 报价确认归档与排序 | ✅ 已完成 | 确认、待确认、报价、历史分组排序；历史接口锁定；商机动作收敛 |
| TASK-026 | 报价单收货信息提取 | ✅ 已完成 | 生成订单表单新增提取按钮；服务端读取 Sheet1 A2/A1 与 B3，兼容持久化内容与旧文件回读 |
| TASK-027 | 取消已发货状态 | ✅ 已完成 | `待发货 → 已完成`；历史 shipped 收敛、状态日志兼容、前端进度条与统计同步 |
| TASK-028 | 客户来源与手机号不变量 | ✅ 已完成 | 客户建档旁路关闭；CSV 默认导入线索；手机号只读且 409 拒绝修改；ADR 与回归已补齐 |
| TASK-029 | 外部 Bearer Token 与新增线索 | ✅ 已完成 | `v2_023` 增加 Token、用户启用和创建人字段；外部接口返回 201；SQLite/MySQL 脚本与模板对齐 |
| TASK-030 | 外部按手机号新增跟进 | ✅ 已完成 | `v2_024` 新增跟进创建人；外部与页面复用 `followup_service`；失败回滚文件与业务数据 |
| TASK-031 | 外部批量手机号校验 | ✅ 已完成 | Bearer 鉴权复用；批量规范化、去重、非法位置、未删除线索口径和隐私响应已覆盖 |
| TASK-032 | 外部写接口幂等重试 | ✅ 已完成 | `v2_025` 幂等缓存、30 天清理、响应回放/冲突、附件摘要和事务原子性已覆盖 |
| TASK-033 | 外部 API 生产更新包 | ✅ 已完成 | 合并迁移与分阶段脚本对齐；fresh/upgrade 启动、只读 preflight/postcheck、Token 占位模板、回滚边界和 API 总文档通过回归 |
| TASK-034 | 代码审查整改 | ✅ 已完成 | 补齐非字符串手机号错误契约；移除重复对象校验和号码比较实现；隔离后端重启并通过健康检查 |

## 4. 验证记录

### 4.1 本次文档任务

验证范围：

- 三份文档路径和章节完整。
- 需求 ID、任务 ID、状态标记和日期符合 `AGENTS.md`。
- PRD、架构与进度中的状态、金额公式和数据规则一致。
- 本次不修改代码，因此不要求重启后端。

执行结果：

- ✅ 隔离 SQLite 全量回归：`Ran 476 tests in 232.154s`，`OK (skipped=2)`。
- ✅ 三份主文档均存在，需求、任务和决策使用稳定 ID。
- ✅ 已核对状态标记、最后更新日期、金额公式和当前迁移版本。
- ✅ 本次变更仅涉及文档，不需要重启后端。

### 4.2 最近一次完整自动化基线

- 时间：2026-11-05
- 命令环境：隔离 SQLite 数据库和上传目录
- 结果：`Ran 473 tests ... OK (skipped=2)`，见 `.local/full-regression-lead-table-final2/full.log`
- 后续提交 `cfdfbd6` 又完成了客户列表与订单线索的视觉修正；本次文档任务重新跑了全量回归，结果为 `Ran 476 tests ... OK (skipped=2)`。
- MySQL 实机测试默认跳过，需显式提供 MySQL 测试凭证并设置 `CRM_TEST_MYSQL=1`。

### 4.3 已知历史测试材料

- `docs/TC-LEADS.md`：92 条线索页手工用例，最近记录为全通过。
- `docs/TC-DEALS.md`：55 条商机页场景，曾记录 6 项失败；多数缺陷在后续提交中处理，发布仍应以当前代码和最新回归为准。
- `ops/T9-T10-上线与验收记录.md`：V1 传统部署的历史现场记录。

### 4.9 TASK-042 跟进历史页分页排序回归

- 定向回归：跟进 API 与前端结构共 19 项新增通过（`tests.test_followups` 分页排序 11 项 + `tests.test_followups_history_ui` 8 项），覆盖分页契约（默认 page=1/size=20、越界页空 items 但 total 不变）、size/page/sort/order 400 边界（含注入样式 sort）、默认 `created_at DESC, id DESC`、显式排序稳定次键 `id DESC`、JOIN 列（客户名/商机阶段）双向排序、`customer`/`deal_stage`/`next_date` NULL 沉底双向、customer_id/deal_id/object_type/object_id 筛选与分页组合、include_system 默认过滤仍在服务端；前端结构覆盖无表单、外壳接入、五个可排序列（附件/操作不可排序）、hash URL 状态、翻页归 1、详情页契约适配、缓存版本断言。连带适配并通过：`tests.test_leads`、`tests.test_csvimport`、`tests.test_aftersales_ui`、`tests.test_aftersale_history_ui`、`tests.test_customer_360_ui`、`tests.test_deal_tag_header_ui`、`tests.test_deals_ui`、`tests.test_followup_modal_ui`、`tests.test_deal_quote_followup_ui`、`tests.test_dashboard_navigation_ui`。
- 全量回归：`Ran 698 tests in 220.377s ... FAILED (failures=4, skipped=2)`：692 通过、2 跳过；4 项失败为分支既有「附件 10/20 上限」测试口径问题（`test_external_api_assets`、`test_external_followups`、`test_followups`、`test_rollout_package`，基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库；本机无常驻后端服务在跑，应用启动经完整测试 lifespan 验证，未做浏览器人工冒烟。

### 4.8 TASK-040 订单列表分页排序回归

- 定向回归：订单 API 与前端结构共 39 项通过（`tests.test_orders` 32 项 + `tests.test_orders_ui` 7 项 + `tests.test_aftersale_history_ui` 缓存断言），覆盖分页契约、size/page/sort/order 400 边界、7 个白名单列全方向、默认 `id DESC`、显式排序 `id DESC` 稳定次键、总额/状态/产品名/订单名称排序、JOIN 列客户名双向排序、`order_name`/`logistics` NULL 沉底双向、customer_id/status/deal_id 筛选与分页组合，以及外壳接入/可排序列（已收/未收/操作不可排序）/hash URL/翻页归 1/缓存版本断言。
- 全量回归：`Ran 664 tests in 552.111s ... FAILED (failures=4, skipped=2)`：658 通过、2 跳过；4 项失败为分支既有「附件 10/20 上限」测试口径问题（`test_external_api_assets`、`test_external_followups`、`test_followups`、`test_rollout_package`，基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库；本机无常驻后端服务在跑，应用启动经完整测试 lifespan 验证，未做浏览器人工冒烟。

### 4.7 TASK-039 售后列表分页排序回归

- 定向回归：售后 API 与前端结构共 37 项通过（`tests.test_aftersales` 26 项 + `tests.test_aftersales_ui` 8 项 + `tests.test_aftersale_history_ui` 3 项），覆盖分页契约、size 白名单 400 边界、默认 `created_at DESC, id DESC`、显式排序稳定次键、JOIN 列（客户名/订单号）双向排序、`problem` NULL 沉底双向、状态/订单/客户筛选与排序组合，以及外壳接入/可排序列/hash URL/翻页归 1/缓存版本断言。
- 全量回归：`Ran 641 tests in 190.512s ... FAILED (failures=4, skipped=2)`：635 通过、2 跳过；4 项失败为分支既有「附件 10/20 上限」测试口径问题（`test_external_api_assets`、`test_external_followups`、`test_followups`、`test_rollout_package`，基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库；本机无常驻后端服务在跑，应用启动经完整测试 lifespan 验证，未做浏览器人工冒烟。

### 4.6 TASK-038 产品列表分页排序回归

- 定向回归：产品 API 与前端结构共 24 项通过（`tests.test_products`、`tests.test_products_ui`），覆盖分页契约、白名单 400 边界、默认天窗优先、显式排序 NULL 沉底、服务端筛选、筛选+分页组合，以及外壳接入/hash URL/翻页归 1/缓存版本断言；连带适配 `test_deal_quotes.py`、`test_multi_product_orders.py`、`test_form_layout.py`、`test_deal_product_consistency.py` 并通过。
- 全量回归：`Ran 624 tests in 210.861s ... FAILED (failures=4, skipped=2)`：618 通过、2 跳过；4 项失败为分支既有「附件 10/20 上限」测试口径问题（`test_external_api_assets`、`test_external_followups`、`test_followups`、`test_rollout_package`，基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库；本机无常驻后端服务在跑，应用启动经完整测试 lifespan 验证，未做浏览器人工冒烟。

### 4.5 TASK-037 商机列表分页排序回归

- 定向回归：`Ran 92 tests ... OK`，覆盖商机 API 新契约、订单/字典/跟进既有适配与前端结构测试。
- 全量回归：`Ran 610 tests ... FAILED (failures=4, skipped=2)`：606 通过、2 跳过；4 项失败为分支既有「附件 10/20 上限」测试口径问题（基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库。

### 4.4 本次商机归档只读回归

- 定向回归：`Ran 96 tests ... OK`，覆盖商机字段、备注、标签、报价、跟进入口和缓存版本断言。
- 全量回归：`Ran 478 tests in 317.105s ... OK (skipped=2)`。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库。
- 验证结果：生成订单后商机更新和标签新增/删除均返回 `409`，商机与标签数据保持不变。
- 验证结果：详情页不显示记跟进、添加/删除标签、添加报价和标记流失等不可执行按钮。

### 4.5 本次工作台数字卡导航回归

- 定向测试：`python -m unittest tests.test_dashboard_navigation_ui tests.test_ui_polish tests.test_customer_360_ui tests.test_deal_tag_header_ui tests.test_followup_phrase_ui tests.test_order_detail_ui`，30 项通过。
- 全量回归：`Ran 481 tests in 208.970s ... OK (skipped=2)`，使用隔离 SQLite 数据库与上传目录。
- 浏览器验证：点击“今日待跟进”和“已逾期”后 URL 均保持 `#/dashboard`，滚动到“今日待跟进”，焦点落在该区标题。
- 验证结果：开启减少动态效果时使用即时滚动；前端脚本版本更新为 `20261105dashboard-scroll1`，Service Worker 缓存更新为 `crm-shell-v79`。

### 4.6 本次工作台跟进与售后概览回归

- 定向测试：工作台接口、导航结构和统计工作台共 29 项通过；表单布局与导航结构复验共 19 项通过。
- 全量回归：`Ran 484 tests in 190.183s ... OK (skipped=2)`，使用隔离 SQLite 数据库与上传目录。
- 接口验证：已完成和已拒绝售后不进入 `active_aftersales_count` 与 `recent_aftersales`；提醒列表最多 4 条，但计数返回全部未完成数量。
- 浏览器验证：今日待跟进操作为“跟进”，点击进入关联商机 `#/deals/3`；无关联商机时进入客户详情。
- 浏览器验证：第四张卡片显示“进行中售后”；当前两笔已完成售后不计入，售后提醒显示未完成空态。
- 后端已按规则重启，`GET /health` 返回 `200`；前端脚本版本更新为 `20261105dashboard-active1`，Service Worker 缓存更新为 `crm-shell-v80`。

### 4.7 本次订单名称与历史收件地址回归

- 定向回归：迁移 18 项、订单/地址/报价核心 16 项、相关 UI/缓存 52 项通过。
- 全量回归：`Ran 486 tests in 237.377s ... OK (skipped=2)`，使用隔离 SQLite 数据库与上传目录。
- 验证结果：客户已确认报价单生成订单时，订单名称与报价单标题一致；订单名称可修改，订单编号修改请求被拒绝。
- 验证结果：生成订单和修改订单均读取 `customer_addresses`，选择历史地址后自动填充收货人、电话和地址。
- 后端已按规则重启，`GET /health` 返回 `200`；本地库迁移版本为 `v2_020`，现有 3 张订单均已完成名称回填。
- 浏览器烟雾验证未执行：Computer Use 无法安全识别 Chrome 当前 URL，因此仅完成自动化 UI 结构检查；留待人工确认视觉与交互。
- 前端脚本版本更新为 `20261109order-name1`，Service Worker 缓存更新为 `crm-shell-v81`。

### 4.8 本次报价确认归档与排序回归

- 定向回归：报价、商机报价 UI、订单详情、缓存版本相关 68 项通过。
- 全量回归：`Ran 489 tests in 297.759s ... OK (skipped=2)`，使用隔离 SQLite 数据库与上传目录。
- 数据迁移：`v2_021` 将存量“客户已确认 + 其他待确认/报价”统一收敛为其他报价历史。
- 验证结果：客户确认报价单后，同一商机其他报价单立即转为历史；历史报价单删除、作废及关联跟进均返回 `409`。
- 验证结果：报价列表按“客户已确认 > 待客户确认 > 报价 > 历史”排序，同状态按更新时间倒序。
- 验证结果：客户确认后商机操作区不显示添加报价单和标记流失，只保留生成订单；生成订单后的整商机快照锁沿用既有回归。
- 前端脚本版本更新为 `20261109quote-history1`，Service Worker 缓存更新为 `crm-shell-v82`。

### 4.9 本次报价单收货信息提取回归

- 定向回归：报价接口与前端结构共 20 项通过。
- 全量回归：`Ran 493 tests in 259.442s ... OK (skipped=2)`，使用隔离 SQLite 数据库与上传目录。
- 示例 Excel：Sheet1 A2 提取为收货人“闫青合”、电话“13954033896”；B3 提取为“山东省 菏泽市 东明县 焦元乡1号新村 德邦包邮”。
- 验证结果：缺收货人电话或地址时返回 `quote_recipient_not_found` 并提示手动填写；多张产品下单表信息不一致时返回 `quote_recipient_conflict`，不自动覆盖。
- 前端脚本版本更新为 `20261109quote-recipient1`，Service Worker 缓存更新为 `crm-shell-v83`。
- 后端已重启，进程 `9684`；`GET /health` 返回 `200`，本地库迁移版本保持 `v2_021`。

### 4.10 本次取消已发货状态回归

- 定向回归：迁移、订单状态机、物流、工作台、统计和相关前端结构共 117 项通过。
- 隔离 SQLite 全量回归：`Ran 498 tests`，`OK (skipped=2)`。
- 验证结果：`ready_to_ship` 只能推进到 `completed`；请求目标状态 `shipped` 返回 `invalid_transition`。
- 验证结果：确认发货会保存物流联系人、运单号、发货时间和完成时间；确认时新增未收运费返回 `payment_incomplete`，订单保持待发货。
- 数据迁移：`v2_022` 将存量 `orders.status='shipped'` 收敛为 `completed`，保留原历史日志并新增自动完成日志；订单状态字典中的 `shipped` 项软删除。
- 前端脚本版本更新为 `20261109order-complete1`，Service Worker 缓存更新为 `crm-shell-v84`。

### 4.11 本次客户来源与手机号不变量回归

- 定向回归：客户、客户编辑 UI、CSV 导入、字典、标签和线索转化共 139 项通过。
- 隔离 SQLite 全量回归：`Ran 506 tests in 167.152s`，`OK (skipped=2)`。
- 验证结果：`POST /api/crm/customers` 返回 405 `customer_create_forbidden`，列表和数据库均无新客户。
- 验证结果：CSV 省略 `target` 时导入线索；JSON 与 multipart 指定 `customers` 均返回 400 `customer_import_forbidden`，不写客户或线索。
- 验证结果：客户更新只要包含 `phone` 即返回 409 `customer_phone_immutable`，同请求的其他字段和 `updated_at` 均不变化。
- 验证结果：客户编辑页电话只读、不提交；线索转化仍原子创建客户和首个商机，并迁移标签、历史跟进及转化引用。
- 前端脚本版本更新为 `20261114customer-phone1`，Service Worker 缓存更新为 `crm-shell-v85`。
- 本次未重启生产后端、未连接真实 MySQL、未审计生产存量客户；这些发布动作留待上线包任务。

### 4.12 本次外部 Bearer Token 与新增线索回归

- 定向回归：外部线索契约、部署资产、迁移、数据库兼容、健康检查、线索、CSV、字典和认证共 150 项通过。
- 隔离 SQLite 全量回归：`Ran 516 tests in 176.160s`，`OK (skipped=2)`。
- 验证结果：缺失、格式错误、未知、过期、撤销、软删除 Token、停用用户和 Cookie-only 调用统一返回 401 `unauthorized`。
- 验证结果：手机号规范化、可选业务字段、标签去重、API 来源、`other` 类型默认、`created_by`、有效重复冲突和软删除排除均符合契约。
- 验证结果：SQLite 更新脚本可从 v2_022 收敛到应用迁移后的 `v2_023`；MySQL 定稿结构和一次性 Token 模板包含标准审计列且无外键。
- 本次未连接真实 MySQL、未初始化真实 Token、未部署生产环境；真实 MySQL 写链路与线上发布仍需对应环境验证。

### 4.13 本次外部新增跟进回归

- 定向回归：外部跟进、页面跟进、附件、部署资产、迁移和数据库兼容共 69 项通过。
- 隔离 SQLite 全量回归：`Ran 526 tests in 192.371s`，`OK (skipped=2)`。
- 验证结果：手机号匹配客户优先、线索回退；无匹配、客户/线索歧义和唯一关闭线索分别返回稳定 404/409 错误。
- 验证结果：外部跟进支持多个附件，沿用 10 个文件、20MB 和文件类型白名单；字段或附件失败不写数据库和文件。
- 验证结果：数据库附件写入失败会回滚跟进、附件和线索状态，并删除该请求已经写出的文件。
- 验证结果：外部 Token 与页面 Cookie 新增跟进都写入 `follow_ups.created_by`；历史行为空。
- 迁移 `v2_024` 及 SQLite/MySQL 更新脚本新增可空 `created_by`，定稿结构和应用迁移一致。
- 本次未连接真实 MySQL、未执行生产上传目录清理、未部署生产环境；真实 MySQL 与线上验收仍待对应环境执行。

### 4.14 本次外部批量手机号校验回归

- 定向回归：手机号校验、外部线索、迁移、数据库兼容和线索模块共 96 项通过。
- 隔离 SQLite 全量回归：`Ran 523 tests in 215.224s`，`OK (skipped=2)`。
- 验证结果：1 和 500 个合法值成功，空数组和 501 个值返回 400 `validation_failed`。
- 验证结果：非法批次整体返回 400 `invalid_phone`，`invalid_positions` 为从 0 开始的原始输入位置。
- 验证结果：输入规范化后按首次出现顺序去重；converted/invalid 未删除线索算存在，软删除线索不算存在。
- 验证结果：响应只含 `phone` 和 `exists`；仅存在客户记录的号码不会误报为线索存在。

### 4.15 本次外部写接口幂等重试回归

- 定向回归：幂等契约、外部线索、外部跟进、迁移、数据库兼容和部署资产共 59 项通过。
- 隔离 SQLite 全量回归：`Ran 543 tests in 204.600s`，`OK (skipped=2)`。
- 验证结果：相同线索或跟进请求带相同 Token、端点和 Key 时回放首次 201 JSON；数据库行数、附件行数和上传文件数不增加。
- 验证结果：相同身份改用不同线索字段、跟进正文或附件时返回 409 `idempotency_conflict`。
- 验证结果：不同 Token 和不同外部写端点可复用同一 Key；缓存记录包含请求摘要、响应状态、响应体和 30 天过期时间。
- 验证结果：过期记录被清理后同一 Key 可重新使用；缓存与业务写入处于同一事务。
- 迁移 `v2_025` 为 SQLite/MySQL 定稿结构和部署 SQL 新增 `api_idempotency_records`，含标准审计列且无外键。
- 本次未连接真实 MySQL、未执行生产数据库更新、未部署生产环境；真实 MySQL 与线上重试行为仍需对应环境验收。

### 4.16 本次外部 API 生产更新包回归

- 定向回归：更新包、三个外部端点、迁移、部署资产、数据库兼容和幂等共 75 项通过。
- 隔离 SQLite 全量回归：`Ran 552 tests in 204.599s`，`OK (skipped=2)`。
- 验证结果：`v2_022 -> v2_025` SQLite 合并脚本与应用迁移的逻辑表、列、索引、审计触发器和版本记录一致；fresh install 与 upgrade fixture 均可启动并通过 `/health`。
- 验证结果：MySQL 合并脚本和只读审计脚本通过现有 `sqlglot` MySQL 解析路径；标准审计列和无外键约束由兼容测试覆盖。
- 验证结果：preflight 可报告无来源客户、无活跃商机、来源手机号不一致和同客多来源线索，且脚本无写操作。
- 验证结果：postcheck 覆盖版本、字段、审计列、字典、有效 Token、幂等表和客户不变量；缺失有效 Token 时 `active_api_token` 返回 `FAIL`。
- 验证结果：上线手册包含 preflight、备份、一次性更新、应用启动、Token 初始化、postcheck、冒烟、开放流量和恢复边界。
- 本次未连接真实 MySQL、未执行生产备份恢复、未初始化真实 Token、未部署生产环境；这些必须在发布窗口由运维执行。

### 4.17 本次代码审查整改回归

- 定向回归：外部线索、跟进、手机号校验、幂等、页面跟进和线索模块共 97 项通过。
- 隔离 SQLite 全量回归：`Ran 553 tests in 195.901s`，`OK (skipped=2)`。
- 验证结果：手机号批次中的 `null`、数字、对象等非字符串项与普通非法号码使用同一 400 `invalid_phone` 响应，并返回全部从 0 开始的位置。
- 验证结果：页面跟进和外部跟进复用同一对象类型校验；合法/非法历史号码统一使用一个比较键。
- 验证结果：外部接口测试复用统一 Token 夹具，保留 Token 生命周期、停用用户和跨端点隔离覆盖。
- 后端验证：使用隔离 SQLite 数据库和上传目录启动新 uvicorn 进程，`GET /health` 返回 `200` 与 `status=ok`，验证后停止该临时进程。
- 本次未连接真实 MySQL、未执行生产迁移或部署；上线前仍需按 `ops/ROLLOUT-EXTERNAL-API.md` 执行生产验证。


### 4.18 本次客户列表外壳与上次跟进列回归

- 定向回归：`Ran 125 tests ... OK`，覆盖客户/标签/线索 API 与列表外壳前端结构断言。
- 全量回归：`Ran 589 tests in 227.776s ... FAILED (failures=4, skipped=2)`；4 项失败均为分支既有「附件 10/20 上限」口径问题（`test_external_api_assets`、`test_external_followups`、`test_followups`、`test_rollout_package`，基线 e912464 同样失败），与本任务无关。
- 验证环境：隔离 SQLite 数据库与上传目录；未使用生产库，未连接真实 MySQL。
- 前端 `node --check static/views/customers.js` 语法检查通过；未做浏览器人工冒烟。

## 5. 遗留问题与风险

| ID | 问题 | 状态 | 影响 | 下一步 |
| --- | --- | --- | --- | --- |
| ISSUE-001 | 旧专题文档仍保留“待开工”、旧阶段、旧外键示例和历史测试失败记录 | 🚧 进行中 | 新成员可能误读 | 以三份主文档为准，后续按需标记废弃 |
| ISSUE-002 | MySQL 真实写链路未在当前环境执行 | 📋 待办 | 无法确认目标库运行时兼容 | 配置隔离 MySQL，执行迁移、写入、备份和恢复 |
| ISSUE-003 | 本次文档任务未执行真实浏览器人工冒烟 | 📋 待办 | 自动化结构测试不能完全覆盖视觉和交互 | 发布前在桌面与 375px 手机宽度逐页验证 |
| ISSUE-004 | 生产环境当前版本与本地提交的部署状态未核验 | 📋 待办 | 无法确认线上就是最新代码 | 发布前记录服务版本、迁移版本和回滚点 |
| ISSUE-005 | SQLite 旧 DDL 仍有 `REFERENCES` 声明 | 📋 待办 | 与“表字段不允许有外键”的硬规则存在历史差异 | 后续单独迁移清理，并补测试；本对话不改代码 |
| ISSUE-006 | 生产存量客户尚未执行来源线索和手机号一致性审计 | 📋 待办 | 历史异常数据不能自动判断或修补 | 上线前只读审计并交人工处理，不在迁移中伪造线索 |

当前没有阻塞核心开发的产品需求问题。上述事项均应在发布或在对应环境验证时关闭。

## 6. 下一步建议

1. 由用户审阅三份主文档，重点确认报价单、商机阶段命名、订单金额和售后口径。
2. 完成一次真实浏览器验收：线索→客户→报价单→确认→订单→收款→完成→售后。
3. 在具备 MySQL 的环境执行 `DATABASE-SQLITE-TO-MYSQL.md` 的迁移、备份与回滚演练。
4. 发布前确认前端 `?v=` 与 `sw.js` 缓存版本一致。
5. 发布后记录后端健康状态、迁移版本、备份文件与回滚点。
6. 将旧文档中已经失效的口径标注废弃，但保留历史，不做静默删除。

## 7. 变更日志

### 2026-11-19 · TASK-043 · 列表外壳推广代码审查整改

- 来源：`[实现中发现约束]`，分支 `codex/list-pagination-sort`（基线 b02abdb）代码审查发现两处缺陷，一次性修复。
- 修复商机出单弹层物流公司下拉：`openDealOrderModal` 中遗留一行 `carrierList = (list || []).filter(...)`，`list` 在该回调作用域已不存在，运行期抛 ReferenceError 导致物流公司下拉永远空白；删除遗留行，只保留 `carrierList = ((res && res.items) || [])` 版本。
- `index.html` shared.js 缓存版本刷新为 `?v=20261119list-shell1`：shared.js 在本分支新增整套列表外壳（`bindListShell`/`listPagerHtml`/`LIST_PAGE_SIZES`/dataTable 排序支持），全部 8 个迁移页依赖它，继续下发旧版本缓存会让回访用户每个列表页都报 `bindListShell is not defined`。
- 顺带修复同类缓存问题：deals.js 本次内容有变，而现版本 `?v=20261119followup-items1` 已随上述缺陷进入用户缓存，同步刷新为 `?v=20261119review-fixes1`；既有缓存断言测试 `test_customer_360_ui.py`/`test_followup_phrase_ui.py`（shared.js）与 `test_deals_ui.py`/`test_followups_history_ui.py`（deals.js）同步更新。
- 新增前端结构测试 `tests/test_ui_polish.py::test_list_shell_cache_and_deals_carrier_dropdown`：index.html 含 shared.js 新版本、deals.js 不再有遗留 `carrierList = (list || [])` 行、`carrierList = ((res && res.items) || [])` 在全文件恰好出现一次。
- 定向 UI 测试与全量回归结果见提交说明；未连接真实 MySQL 验证，未做浏览器人工冒烟。

### 2026-11-19 · TASK-042 · 跟进历史页去除表单并接入分页排序

- 来源：`[用户明确要求]`，GitHub issue #16（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/follow-ups`：响应从全量数组改为 `{items,total,page,size}`；新增 `page`/`size`/`sort`/`order`，复用 Ticket #9/#13 同一套校验口径（`LIST_PAGE_SIZES` 白名单与 `invalid_page`/`invalid_page_size`/`invalid_sort`/`invalid_order` 400 错误码）；`sort` 白名单 `customer`（JOIN `c.name`）/`deal_stage`（JOIN `d.stage`）/`content`/`next_date`/`created_at`，排序 SQL 只来自 `_FOLLOWUP_SORT_SQL` 服务端映射；`customer`/`deal_stage`/`next_date` 可空升/降序均 NULL 沉底，显式排序稳定次键 `id DESC`；未传 sort 维持既有默认 `created_at DESC, id DESC`。`customer_id`/`deal_id`/`object_type`/`object_id`/`include_system` 筛选保留且仍全部服务端执行，与分页排序自由组合；照片明射只对当页数据计算。
- 前端跟进历史页重构：删除「记一条跟进」表单及 `followupFormHtml`/`followupItemHtml`（“记跟进”统一走各业务对象详情页的 `openFollowModal` 弹层，本次不动）；改为纯跟进流水表格并接入共享列表外壳：客户/商机阶段/跟进内容/下次跟进/记录时间五个可排序表头（附件/操作不可排序），页码按钮 + 每页条数；`customer`/`deal` 深链筛选与 `page/size/sort/order` 一起写入 `#/followups` hash URL（`history.replaceState`），改排序/条数/筛选均回第 1 页；删除操作保留（删完刷新当页）；工作台「查看全部跟进」`链接 `#/followups` 路由不变。
- 连带适配：售后/客户/商机/线索详情页履历调用改用 `size=500` 取全量并读 `.items`；`index.html` 跟进页与四个详情页脚本缓存版本刷新（`20261119followup-list-shell1` / `20261119followup-items1`），`test_aftersales_ui.py`/`test_aftersale_history_ui.py`/`test_customer_360_ui.py`/`test_deal_tag_header_ui.py`/`test_deals_ui.py` 缓存断言同步更新。
- 既有测试适配新契约：`test_followups.py`/`test_leads.py`/`test_csvimport.py`/`test_customers.py`/`test_deal_quotes.py`/`test_lead_quick_tags.py` 中 GET /follow-ups 数组断言改取 `["items"]`；`test_form_layout.py` 移除跟进页 `fuForm` 表单断言（表单按 issue #16 删除）。
- 新增 API 测试 11 项（分页契约、size/page/sort/order 400 边界、默认排序、显式排序稳定次键、JOIN 列双向、NULL 沉底双向、筛选+分页组合、include_system 服务端过滤）与前端结构测试 `tests/test_followups_history_ui.py` 8 项（无表单、外壳接入、可排序列、hash URL、翻页归 1、契约适配、缓存版本）。
- 定向 `tests/test_followups.py` 与 `tests/test_followups_history_ui.py` 共 35 项通过（含 1 项既有附件上限失败）；隔离 SQLite 全量回归 692 通过、2 跳过（MySQL live 自跳过），4 项失败为分支既有「附件 10/20 上限」测试口径问题（基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 未连接真实 MySQL 验证；未做浏览器人工冒烟。


### 2026-11-19 · TASK-041 · 物流公司列表服务端分页、排序与筛选

- 来源：`[用户明确要求]`，GitHub issue #15（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/carriers`：响应从全量数组改为 `{items,total,page,size}`；复用 Ticket #9/#13 同一套校验口径（`LIST_PAGE_SIZES` 白名单与 `invalid_page`/`invalid_page_size`/`invalid_sort`/`invalid_order` 400 错误码）；`sort` 白名单 `name`（公司名称）/`address`（地址），排序 SQL 只来自 `_CARRIER_SORT_SQL` 服务端映射；`address` 可空升/降序均 NULL 沉底，显式排序稳定次键 `id DESC`；未传 sort 按 issue #8 物流页默认口径：被订单关联次数倒序（`_ORDER_COUNT_SQL` 服务端白名单子查询，绝不接收客户端输入，且不是可排序列）→ `id DESC`。`q` 关键词（公司名/编号/主联系人/电话/地址 + 多联系人姓名/电话，`ESCAPE '\'` 通配符转义）与 `active`（仅看启用）筛选全部服务端执行，与分页排序自由组合。
- 顺带修复潜在缺陷：`update_carrier` 的 assignments 白名单漏了 `is_active`，停用/启用从未落库（前端停用按钮实际无效）；「仅看启用」筛选服务端化后该字段必须真的可写，补测试覆盖。
- 前端物流页接入共享列表外壳：公司名称/地址两个可排序表头（联系人/电话/被订单关联/操作不可排序），页码按钮 + 每页条数；仅看启用、关键词筛选与 `page/size/sort/order` 一起写入 `#/logistics` hash URL（`history.replaceState`），改排序/条数/任一筛选均回第 1 页；本地整表加载 + 前端过滤/排序移除；表头计数徽标改由 `res.total` 填充，原「共被订单关联 N 次」全量统计随全量加载一并移除。
- 连带适配：订单编辑/发货弹层、商机出单弹层的物流公司下拉改用 `/carriers?size=500` + `res.items`；`index.html` 物流/订单/商机脚本缓存版本刷新（`20261119carrier-list-shell1` / `20261119carrier-items1`），`test_orders_ui.py` / `test_deals_ui.py` / `test_aftersale_history_ui.py` 缓存断言同步更新。
- 既有测试适配新契约：`tests/_util.py::create_carrier` 409 复用分支、`test_addresses_contacts.py` 数组断言改取 `items`（`size=500`）。
- 新增 API 测试（分页契约、size/page/sort/order 400 边界、默认被订单关联次数倒序 + `id DESC` 次键、计算列不可排序、name/address 双向、address NULL 沉底双向、同值次键 `id DESC`、关键词命中公司名/地址/联系人、LIKE 通配符转义、active=1/0 筛选、筛选+分页/排序组合）与前端结构测试 `tests/test_logistics_ui.py`（外壳接入、可排序列、hash URL 含 active+q+page/size/sort/order、翻页归 1、下拉契约适配、缓存版本断言）。
- 定向 `tests/test_carriers.py` 14 项、`tests/test_logistics_ui.py` 9 项全部通过；隔离 SQLite 全量回归 675 通过、2 跳过（MySQL live 自跳过），4 项失败为分支既有「附件 10/20 上限」测试口径问题（基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 未连接真实 MySQL 验证；未做浏览器人工冒烟。


### 2026-11-18 · TASK-040 · 订单列表服务端分页与排序

- 来源：`[用户明确要求]`，GitHub issue #12（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/orders`：响应从全量数组改为 `{items,total,page,size}`；复用 Ticket #9/#13 同一套校验口径（`LIST_PAGE_SIZES` 白名单与 `invalid_page`/`invalid_page_size`/`invalid_sort`/`invalid_order` 400 错误码）；`sort` 白名单 `order_name`/`customer`（LEFT JOIN `customers.name`，客户软删后名字 NULL 沉底、订单仍在列表）/`product`（`product_name_snapshot`）/`total`（`amount`）/`logistics`（`logistics_mode`）/`status`/`created_at`，排序 SQL 只来自 `_ORDER_SORT_SQL` 服务端映射；可空列（`order_name`/`customer`/`product`/`logistics`）升/降序均 NULL 沉底，显式排序稳定次键 `id DESC`，未传 sort 默认编号倒序 `id DESC`；列表补 `is_delete = 0` 过滤对齐项目数据库规则；`customer_id`/`status`/`deal_id` 筛选全部服务端执行，与分页排序自由组合。
- 前端订单页接入共享列表外壳：订单名称/客户/产品/总额/物流/状态/创建时间 7 个可排序表头（已收/未收为计算列、操作列不可排序），页码按钮 + 每页条数；状态 Tab 与 `page/size/sort/order` 一起写入 `#/orders` hash URL（`history.replaceState`），改排序/条数/页签均回第 1 页；本地 `pagerHtml(res)` 调用移除（该函数对本视图本就未定义，翻页区会 ReferenceError，属顺带修复的潜在缺陷）。
- `index.html` 订单页脚本缓存版本刷新为 `20261118order-list-shell1`，`test_aftersale_history_ui.py` 缓存断言同步更新。
- 既有测试适配新契约：`test_orders.py::test_list_orders` 的数组断言改取 `items`/`total`。
- 新增 API 测试（分页契约、size/page/sort/order 400 边界、7 个白名单列全方向、默认 `id DESC`、显式排序稳定次键、总额/状态排序、JOIN 列客户名双向、产品名/订单名称排序、`order_name`/`logistics` NULL 沉底双向、筛选 + 分页组合）与前端结构测试 `tests/test_orders_ui.py`（外壳接入、可排序列、hash URL 含状态 + page/size/sort/order、翻页归 1、缓存版本断言）。

### 2026-11-18 · TASK-039 · 售后列表服务端排序与共享外壳

- 来源：`[用户明确要求]`，GitHub issue #11（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/aftersales`：已有 page/size 基础上补齐 Ticket #9 同款校验口径（复用 `LIST_PAGE_SIZES` 白名单与 `invalid_page`/`invalid_page_size`/`invalid_sort`/`invalid_order` 400 错误码）；`sort` 白名单 `aftersale_no`（`a.no`）/`type`/`order`（JOIN `orders.order_no`）/`customer`（JOIN `customers.name`）/`problem`（`a.description`）/`status`/`created_at`，排序 SQL 只来自 `_AFTERSALE_SORT_SQL` 服务端映射；`problem` 按可空防御处理（升/降序均 NULL 沉底），显式排序稳定次键 `id DESC`，未传 sort 默认 `created_at DESC, id DESC`；`status`/`order_id`/`customer_id`/`sla_overdue` 筛选全部服务端执行，与分页排序自由组合。
- 模型：`AftersaleOut.description` 放宽为可空（新建口径仍必填；早期库/手工数据可能残留 NULL，列表/详情按可空容忍，避免排序带出 NULL 行时响应 500）。
- 前端售后页接入共享列表外壳：售后单号/类型/订单/客户/问题/状态/创建时间 7 个可排序表头（操作列不可排序），页码按钮 + 每页条数；三态状态页签与 `page/size/sort/order` 一起写入 `#/aftersales` hash URL（`history.replaceState`），改排序/条数/页签均回第 1 页；本地 `pagerHtml`/`PAGE_SIZE` 移除（修复售后列表翻页区引用不存在函数的潜在 ReferenceError）。
- `index.html` 售后页脚本缓存版本刷新为 `20261118aftersale-list-shell1`，`test_aftersale_history_ui.py` 缓存断言同步更新。
- 新增 API 测试（默认口径、显式排序稳定次键、size/page 400 边界、分页窗口、非法 sort/order 400、JOIN 列双向排序、单号/类型排序、`problem` NULL 沉底双向、筛选 + 排序组合）与前端结构测试 `tests/test_aftersales_ui.py`（外壳接入、可排序列、hash URL 含状态/订单/客户筛选 + page/size/sort/order、翻页归 1、缓存版本断言）。

### 2026-11-18 · TASK-038 · 产品列表服务端分页、排序与筛选

- 来源：`[用户明确要求]`，GitHub issue #14（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/products`：响应从全量数组改为 `{items,total,page,size}`；复用 Ticket #9/#13 同一套校验口径（`LIST_PAGE_SIZES` 白名单与 `invalid_page`/`invalid_page_size`/`invalid_sort`/`invalid_order` 400 错误码）；`sort` 白名单 `product`（按名称）/`drive_type`/`status`（即 `is_active`），排序 SQL 只来自 `_PRODUCT_SORT_SQL` 服务端映射；`drive_type` 可空升/降序均 NULL 沉底，显式排序稳定次键 `id DESC`；未传 sort 默认维持产品页既有口径：天窗分类优先 → `series` → `code` → `id DESC`。`q`/`category`/`series`/`drive_type`/`is_active` 筛选全部服务端执行，与分页排序自由组合。
- 前端产品页接入共享列表外壳：`产品`/`驱动`/`状态` 三个可排序表头（配置/规格范围/引用/操作不可排序），页码按钮 + 每页条数；keyword/分类/系列/驱动/状态五个筛选条件与 `page/size/sort/order` 一起写入 `#/products` hash URL（`history.replaceState`），改排序/条数/任一筛选均回第 1 页；本地整表加载 + `filterProducts` 前端过滤移除；列表「编辑」改为按 id 拉详情后打开编辑弹层。
- 连带适配：`shared.js` 产品选择器 `loadProductCatalog` 改用 `size=500` 一次拉全并取 `res.items`；`index.html` 产品页脚本缓存版本刷新为 `20261118product-list-shell1`。
- 既有测试适配新契约：`test_products.py`（种子目录、搜索、停用过滤等数组断言改取 `items`，全量断言改 `size=500`）、`test_deal_quotes.py`、`test_multi_product_orders.py`、`test_form_layout.py`（筛选栏签名变化）。
- 新增 API 测试（分页契约、五个 size 档位、四类 400 边界、默认天窗优先且类内 series/code 升序、`product`/`status` 双向排序、`drive_type` NULL 沉底双向、分类/系列/驱动/关键字筛选、筛选+分页切片一致、筛选+排序组合）与前端结构测试 `tests/test_products_ui.py`（外壳接入、可排序列、hash URL 含五个筛选 + page/size/sort/order、翻页归 1、缓存版本断言）。

### 2026-11-18 · TASK-037 · 商机列表服务端分页与排序

- 来源：`[用户明确要求]`，GitHub issue #13（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/deals`：响应从全量数组改为 `{items,total,page,size}`；复用 Ticket #9/#10 同一套校验口径（`LIST_PAGE_SIZES` 白名单与 `invalid_page`/`invalid_page_size`/`invalid_sort`/`invalid_order` 400 错误码）；`sort` 白名单 `customer/product/model/drive_type/size/amount/stage/updated_at`（`customer` 走 LEFT JOIN `c.name`，`size` 即列表「尺寸」列 `deals.spec`），排序 SQL 只来自 `_DEAL_SORT_SQL` 服务端映射；可空列升/降序均 NULL 沉底，显式排序稳定次键 `id DESC`，未传 sort 默认 `updated_at DESC, id DESC`；`q` 搜索通配符转义对齐线索/客户页口径，`customer_id`/`stage` 筛选与分页共存。
- 前端商机页接入共享列表外壳：8 个可排序表头（客户/产品/型号/手动电动/尺寸/成交报价/阶段/更新时间），操作列不可排序；stage 页签与 `page/size/sort/order` 一起写入 `#/deals` hash URL（`history.replaceState`），改排序/条数/页签均回第 1 页；本地整表加载 + 前端排序移除。
- 连带适配：`followups.js` 跟进弹窗的商机下拉改用 `res.items`（`size=500` 取全量）；`index.html` 商机页与跟进页脚本缓存版本号刷新。
- 既有测试适配新契约：`test_deals_v2.py`、`test_deal_orders.py`、`test_dicts.py`、`test_followups.py` 中按数组取 `GET /deals` 的断言改取 `items`。
- 新增 API 测试（分页契约、size/page/sort/order 400 边界、8 个白名单列全方向、默认 `updated_at DESC, id DESC`、显式排序 `id DESC` 次键、金额/阶段排序、JOIN 列客户名排序、可空列 NULL 沉底双向、筛选与分页共存）与前端结构测试 `tests/test_deals_ui.py`（外壳接入、可排序列、hash URL 含 stage+page+size+sort+order、翻页归 1、缓存版本断言）。
- 定向回归 92 项通过；隔离 SQLite 全量回归 610 项中 606 通过、2 跳过，4 项失败为分支既有「附件 10/20 上限」测试口径问题（基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 未连接真实 MySQL 验证；未做浏览器人工冒烟。

### 2026-11-18 · TASK-036 · 客户列表外壳与上次跟进列

- 来源：`[用户明确要求]`，GitHub issue #10（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/customers`：复用 Ticket #9 同一套校验口径（`LIST_PAGE_SIZES` 白名单与 400 错误码），`sort` 白名单 `name/type/location/intent/last_follow/created_at`，排序 SQL 只来自 `_CUSTOMER_SORT_SQL` 服务端映射；可空列升/降序均 NULL 沉底，显式排序稳定次键 `id DESC`，未传 sort 默认 `id DESC`。
- 响应新增派生字段 `last_follow`：`follow_ups` 中 `object_type='customer'` 且 `kind='follow'` 的最新 `created_at`，无人工跟进为 `null`；系统履历（如编辑档案产生的 `change` 记录）不计入。
- 前端客户页接入共享列表外壳：六个可排序表头（名称/类型/地区/意向/上次跟进/创建时间），标签/微信/商机/订单/累计成交/操作列不可排序；新增「上次跟进」列；`page/size/sort/order` 写入 `#/customers` hash URL（`history.replaceState`），改排序/条数/搜索/标签筛选均回第 1 页且不整页重渲染；客户页本地 `pagerHtml` 移除，分页只走共享外壳。
- `index.html` 客户页脚本缓存版本号刷新（`v=20261118customer-list-shell1`），避免浏览器缓存旧视图脚本导致版本不一致。
- 既有测试适配白名单口径：`test_customers.py::test_pagination` 与 `test_tags.py::test_tag_filter_paginates` 的 `size=2` 改为白名单档位；`test_customer_360_ui.py` 缓存版本断言同步更新。
- 新增 API 测试（size/page/sort/order 400 边界、默认 id DESC、显式排序 id DESC 次键、name/location/last_follow 排序、NULL 沉底双向、last_follow 派生与 kind 过滤）与前端结构测试 `tests/test_customers_ui.py`。
- 定向回归 125 项通过；隔离 SQLite 全量回归 589 项中 585 通过、2 跳过，4 项失败为分支既有「附件 10/20 上限」测试口径问题（基线 e912464 上同样失败），与本任务无关，单独报告不修。
- 未连接真实 MySQL 验证；未做浏览器人工冒烟。

### 2026-11-18 · TASK-035 · 共享列表外壳与线索分页/排序

- 来源：`[用户明确要求]`，GitHub issue #9（父需求 #8 列表页统一分页与可排序表头）。
- 后端 `GET /api/crm/leads`：`page >= 1`、`size` 白名单 `[10,20,50,100,500]`（默认 20）、`sort` 白名单 `type/source/location/intent/last_follow/created_at`、`order asc|desc`；非法一律 400，排序 SQL 只来自服务端白名单映射，`last_follow` 复用派生 `last_follow_at` 表达式；可空列升/降序均 NULL 沉底；显式排序稳定次键 `id DESC`；未传 sort 维持「无效线索沉底 + created_at DESC + id DESC」默认口径。
- 前端 `shared.js` 新增可复用列表外壳：`dataTable` 支持 `sortKey` 列渲染三态（asc → desc → 默认）可排序表头，`listPagerHtml` 提供窗口化页码按钮 + 每页条数选择器，`bindListShell` 统一事件委托（含 Enter/空格键）。
- 线索页接入外壳：六个可排序列（类型/来源/地区/意向/上次跟进/创建时间），标签/微信/操作列不加排序、只读行为不变；`page/size/sort/order` 写入 `#/leads` hash URL（`history.replaceState`，不触发重渲染、不打断搜索框焦点），改排序或每页条数自动回第 1 页，刷新/分享链接状态保持。
- 新增 API 测试（size/page/sort/order 400 边界、NULL 沉底、id DESC 次键、last_follow 派生排序、默认沉底不变）与前端结构测试（外壳导出、三态循环、六列 sortKey、hash URL 状态、翻页/条数归 1）。
- 定向回归 80 项通过；隔离 SQLite 全量回归 571 项中 567 通过、2 跳过，4 项失败为分支既有「附件 10/20 上限」测试口径问题（基线 e912464 上同样失败），与本任务无关。
- 未连接真实 MySQL 验证；未做浏览器人工冒烟。

### 2026-11-17 · 文档整理 · docs 目录归档与索引

- 来源：`[用户明确要求]`
- 新增 `docs/README.md` 文档索引；将 `PLANNER-V2.md`、`BUSINESS-ARCH-V2.md` 归档到 `docs/archive/`。
- 删除已完成的 `DEPLOY-menu-dict-align.md`、已被现行流程取代的 `BUSINESS-MULTI-PRODUCT-ORDER-V1.md`，以及重复或不可运行的 `planner-v2-*` 脚本。
- 本次仅调整文档结构和引用，未改动业务代码；发布仍以当前代码和最新自动化回归为准。

### 2026-11-14 · TASK-034 · 代码审查整改

- 来源：`[实现中发现约束]`，`code-review` Standards/Spec 双轴审查。
- 手机号批量校验对非字符串项不再提前返回 `validation_failed`，统一进入手机号规范化并返回 400 `invalid_phone` 与 `invalid_positions`。
- 页面和外部跟进共享一个对象类型校验函数；线索、客户和跟进匹配共享历史号码比较键。
- 外部 API 测试共用 Token 创建夹具，减少重复生命周期构造并保持原有隔离覆盖。
- 定向回归 97 项通过；隔离 SQLite 全量回归 553 项通过、2 项跳过；隔离后端重启后 `/health` 返回 200。

### 2026-11-14 · TASK-033 · 外部 API 生产更新包

- 来源：`[用户明确要求]`，GitHub issue #7。
- 新增 SQLite/MySQL `v2_022 -> v2_025` 一次性合并更新脚本，覆盖 Token、用户启用、线索/跟进创建人、客户来源字典和幂等表。
- 新增只读 preflight/postcheck：上线前报告客户来源与手机号异常，上线后验证结构、字典、有效 Token、审计列、无外键和客户不变量。
- 新增 `ops/ROLLOUT-EXTERNAL-API.md`，固定执行顺序、备份、一次性操作、健康检查、第三方开放条件和恢复边界；不提供高风险 down migration。
- 合并第三方 API 文档，覆盖三个端点、鉴权、字段/defaults、附件、幂等、限制、状态码和稳定错误码。
- 更新包、三个外部端点、迁移和兼容性定向回归 75 项通过；隔离 SQLite 全量回归 552 项通过、2 项跳过。

### 2026-11-14 · TASK-032 · 外部写接口幂等重试

- 来源：`[用户明确要求]`，GitHub issue #6。
- 外部新增线索和新增跟进支持可选 `Idempotency-Key`；身份按 Token、端点、Key 三元组隔离。
- 相同业务请求回放首次状态码和 JSON；不同线索字段、跟进正文或附件使用同一身份时返回 409 `idempotency_conflict`。
- 幂等缓存保存请求哈希、响应状态/正文、30 天过期时间和标准审计列；过期记录在后续幂等请求前清理。
- 跟进附件文件名、类型、大小和内容摘要参与请求比较；回放不重复写跟进、附件行或文件。
- `v2_025` 同步 SQLite/MySQL 定稿结构、应用迁移和部署 SQL，不引入数据库外键。
- 定向回归 59 项通过；隔离 SQLite 全量回归 543 项通过、2 项跳过。

### 2026-11-14 · TASK-030 · 外部按手机号新增跟进

- 来源：`[用户明确要求]`，GitHub issue #4。
- 新增 `POST /api/external/v1/follow-ups`，使用同一 Bearer Token；手机号匹配客户优先、线索回退，歧义和关闭线索均拒绝。
- 页面与外部 API 复用 `followup_service`，统一执行正文/日期/附件校验、对象守卫、状态流转、附件落盘和创建人审计。
- 支持一次最多 10 个附件、单个 20MB 和既有类型白名单；数据库失败回滚业务数据并清理本次已写文件。
- `v2_024` 为 `follow_ups` 新增可空 `created_by`，同步 SQLite/MySQL 定稿结构和部署 SQL。
- 定向回归 69 项通过；隔离 SQLite 全量回归 526 项通过、2 项跳过。

### 2026-11-14 · TASK-031 · 外部批量校验线索手机号

- 来源：`[用户明确要求]`，GitHub issue #5。
- 新增 `POST /api/external/v1/leads/phone-check`，复用外部 Bearer Token 鉴权，不接受 Cookie。
- 批次限制 1 到 500；所有值先规范化，任一非法时整批返回 400 并带零基 `invalid_positions`；重复值按首次出现顺序去重。
- 只查询未删除线索；converted/invalid 未删除线索算存在，软删除排除。响应只含规范手机号和布尔存在状态，不读取客户明细。
- 外部 API 文档、PRD 和架构补充批次大小、规范化、响应和错误契约。
- 定向回归 96 项通过；隔离 SQLite 全量回归 523 项通过、2 项跳过。

### 2026-11-14 · TASK-029 · 外部 Bearer Token 与新增线索

- 来源：`[用户明确要求]`，GitHub issue #3。
- 新增 `/api/external/v1/leads`，只接受完整 Bearer Token；缺失、格式错误、未知、过期、撤销、软删除和绑定用户停用统一返回 401。
- 手机号规范化为 11 位大陆手机号；外部线索固定来源 `API`、状态 `new`、默认类型 `other`，有效线索/客户重复返回 409 摘要。
- 页面和外部新增线索复用 `lead_service`，均写入 `created_by`；Token 支持多行、可选过期、撤销和用户绑定。
- 迁移 `v2_023` 增加 `api_tokens`、`users.is_active`、`leads.created_by` 和 `customer_source.api`，同步 SQLite/MySQL 定稿结构、更新脚本及一次性 Token 模板。
- 新增外部 API 文档及完整 Token 明文保存、无 IP 白名单 ADR。
- 定向回归 150 项通过；隔离 SQLite 全量回归 516 项通过、2 项跳过。

### 2026-11-14 · TASK-028 · 客户来源与手机号不变量

- 来源：`[用户明确要求]`，GitHub issue #2。
- 客户直接建档接口固定返回 405 `customer_create_forbidden`；CSV 导入目标固定为线索，省略时默认 `leads`，选择 `customers` 返回 400 `customer_import_forbidden`。
- 客户手机号继承来源线索，转客后不可修改；更新请求包含 `phone` 时返回 409 `customer_phone_immutable`，客户编辑页电话只读且不提交。
- 保留现有线索转化事务：客户、首个商机、标签和历史跟进一次性完成，线索写入转化客户和商机引用。
- 新增客户领域术语和 `docs/adr/0001-customer-origin-invariant.md`；生产异常数据只审计报告，不自动伪造来源线索。
- 定向回归 139 项通过；隔离 SQLite 全量回归 506 项通过、2 项跳过。

### 2026-11-10 · TASK-027 · 取消已发货状态

- 来源：`[用户明确要求]`
- 订单活跃状态由“待发货 → 已发货 → 已完成”调整为“待发货 → 已完成”；确认发货成功后订单立即进入已完成状态。
- 后端状态机、数据字典、统计、工作台和订单详情同步移除 `shipped` 活跃状态；历史日志中的 `shipped` 保留“已发货”只读标签。
- 迁移 `v2_022` 将存量 `shipped` 订单自动转为 `completed`，补齐发货/完成时间并记录自动完成日志，同时软删除订单状态字典中的 `shipped` 项。
- 确认发货继续校验物流公司、联络人和运单号；临时增加的运费若导致订单应收高于已收金额，则拒绝完成。
- 前端脚本版本更新为 `20261109order-complete1`，Service Worker 缓存更新为 `crm-shell-v84`。
- 隔离 SQLite 全量回归 498 项通过、2 项跳过。

### 2026-11-09 · TASK-026 · 报价单收货信息提取

- 来源：`[用户明确要求]`
- 生成订单表单在“历史收件人及地址”旁新增“从报价单提取”按钮。
- 服务端新增 `GET /quotes/{quote_id}/shipping-recipient`，从 Sheet1!A2 的“收货人+电话”和 Sheet1!B3 的“收货地址”提取；A2 不完整时兼容 A1，并优先使用已持久化的 Excel 内容快照，旧数据缺少快照时回读原文件。
- 电话会去除分隔空格；收货信息缺失或多产品下单表不一致时提示人工填写，不生成错误覆盖。
- 前端脚本版本更新为 `20261109quote-recipient1`，Service Worker 缓存更新为 `crm-shell-v83`。
- 定向回归 20 项通过；隔离 SQLite 全量回归 493 项通过、2 项跳过。

### 2026-11-09 · TASK-025 · 报价确认归档与排序

- 来源：`[用户明确要求]`
- 报价单列表按 `confirmed > pending > draft > void` 分组，同状态按 `updated_at` 倒序。
- 客户确认报价单时，同一事务内将其他报价单转为历史；历史报价只读，禁止删除、作废和关联新跟进。
- 客户确认后隐藏“添加报价单”“标记流失”，商机操作区只保留“生成订单”。
- 生成订单后继续以 `deals.order_id` 判定整商机快照锁，订单保留产品、价格、参数和下单表快照。
- 前端脚本版本更新为 `20261109quote-history1`，Service Worker 缓存更新为 `crm-shell-v82`。
- 定向回归通过；隔离 SQLite 全量回归 489 项通过、2 项跳过。

### 2026-11-09 · TASK-024 · 订单名称与历史收件地址

- 来源：`[用户明确要求]`
- 新增 `orders.order_name`，客户已确认报价单生成订单时复制报价单名称；迁移 `v2_020` 从来源报价单标题回填历史订单。
- 订单生成表单显示订单名称；产品展示不再拼接产品编号。
- 订单列表、详情主标题和编辑表单显示订单名称；订单编号只读，后端拒绝编号修改。
- 生成订单与修改订单的收货区域均可读取客户历史收件人及地址并自动填充。
- 前端脚本版本更新为 `20261109order-name1`，Service Worker 缓存更新为 `crm-shell-v81`。

### 2026-11-05 · TASK-023 · 工作台跟进详情与未完成售后概览

- 来源：`[用户明确要求]`
- 今日待跟进右侧操作由“记一条”改为“跟进”，移除工作台快捷跟进弹窗；有关联商机时进入商机详情，否则进入客户详情。
- 第四张 KPI 由“超时售后”改为“进行中售后”，显示全部 `pending`/`processing` 售后单准确数量。
- “售后提醒”只展示最近未完成售后单，已完成和已拒绝记录不再出现。
- 新增 `active_aftersales_count` 接口字段；提醒列表最多 4 条，数量不受展示上限影响。
- 前端脚本版本更新为 `20261105dashboard-active1`，Service Worker 缓存更新为 `crm-shell-v80`。
- 隔离 SQLite 全量回归 484 项通过、2 项跳过；本地后端重启并通过健康检查。

### 2026-11-05 · TASK-022 · 工作台待跟进数字卡同页导航

- 来源：`[用户明确要求]`
- “今日待跟进”和“已逾期”数字卡不再进入独立跟进表单，改为滚动到当前工作台“今日待跟进”区域。
- 两张卡都保留键盘可操作语义，点击后同步移动焦点；开启减少动态效果时跳过平滑滚动。
- 其他数字卡和“查看全部”入口保持原行为。
- 前端脚本版本更新为 `20261105dashboard-scroll1`，Service Worker 缓存更新为 `crm-shell-v79`。

### 2026-11-05 · TASK-021 · 已生成订单商机归档只读

- 来源：`[用户明确要求]`
- 商机存在 `order_id` 时按“已生成订单”统一判定为存档状态，基本信息、备注、报价关联数据和已有标签全部只读。
- 后端拒绝商机更新和标签新增/删除；前端隐藏不可执行的跟进、标签、添加报价和标记流失按钮。
- 商机列表中的归档记录操作文案由“跟进”改为“查看”，详情仍保留订单、报价明细和附件等查看入口。
- 前端脚本版本更新为 `20261105deal-archive1`，Service Worker 缓存更新为 `crm-shell-v78`。
- 定向回归 96 项通过；隔离 SQLite 全量回归 478 项通过、2 项跳过。

### 2026-11-05 · TASK-018 · 建立三份项目主文档

- 来源：`[用户明确要求]`
- 新增 `docs/01-prd.md`、`docs/02-arch.md`、`docs/03-progress.md`。
- 以当前代码、最新业务专题文档、Git 历史和隔离测试结果归纳统一口径。
- 明确 PRD、架构和进度三类事实的职责及冲突处理顺序。
- 记录 MySQL 实机验证、真实浏览器冒烟、生产部署核验和 SQLite 遗留外键声明等待办。
- 本任务只修改文档，不修改业务代码，不重启后端。

### 2026-11-05 · TASK-015 · 客户列表与订单线索对齐

- 来源：`[实现中发现约束]`
- 客户列表名称、联系方式和订单链接展示与近期线索页布局重新对齐。
- 关联提交：`cfdfbd6`、`9f69b46`。

### 2026-11-05 · TASK-016 · 数据库迁移与恢复文档

- 来源：`[实现中发现约束]`
- 补齐 SQLite 到 MySQL、MySQL 备份恢复、SQLite 备份恢复文档。
- 关联提交：`c84cedc`。

### 2026-11-05 · TASK-014/TASK-015 · 线索标签、客户 360 与检索体验

- 来源：`[实现中发现约束]`
- 增加线索详情批量标签编辑、今日工作统计、客户 360 渐进履历、地区检索。
- 关联提交：`18ded4a`、`1f8c5d8`、`e3b50f8`、`2808fe3`。

### 2026-11-04 · TASK-016 · MySQL 兼容

- 来源：`[实现中发现约束]`
- 增加 MySQL 结构、SQL 方言适配、迁移工具、备份恢复手册和兼容测试。
- 实际 MySQL 写链路仍需在可用环境执行。
- 关联提交：`8038c12`。

### 2026-11-03 至 2026-11-02 · 前端与跟进体验

- 来源：`[用户明确要求]`、`[实现中发现约束]`
- 完成界面层级、跟进常用短语、Docker 单服务、订单详情、物流联系人、报价作废和历史售后关联等改造。

### 2026-11-02 · TASK-011 至 TASK-013 · 报价、订单和售后闭环

- 来源：`[用户明确要求]`
- 完成多产品报价、优惠与运费拆分、订单收货快照、物流联络人、售后历史关联和完成锁定。

### 2026-11-01 · TASK-010 · 报价单流程

- 来源：`[用户明确要求]`
- 商机改为只维护备注；报价产品、Excel 下单表、金额、预览和客户确认进入报价单。
- 只有客户已确认报价单可生成订单。

### 2026-10-31 · TASK-002 至 TASK-009 · V2 核心闭环

- 来源：`[用户明确要求]`
- 完成线索、客户 360、商机、订单、售后、物流、统一跟进、工作台、统计和数据字典。

### 2026-10-29 · TASK-001 · V1 上线

- 来源：`[用户明确要求]`
- 完成登录、基础客户/商机、附件、部署、备份和 V1 验收。
