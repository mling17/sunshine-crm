# docs 文档索引

> 最后整理：2026-11-17
>
> 阅读优先级：`01-prd.md` > `02-arch.md` > `03-progress.md` > 其他文档。旧方案、页面草稿和测试记录可以解释背景，不能覆盖主文档。

## 核心事实源

| 文档 | 用途 |
| --- | --- |
| `01-prd.md` | 产品需求、业务规则和验收标准的唯一事实来源 |
| `02-arch.md` | 系统实现、模块边界、数据模型和技术决策 |
| `03-progress.md` | 当前进度、验证记录、遗留问题和下一步 |
| `adr/` | 架构决策记录，改动相关区域前先读 |
| `agents/` | Agent 工作流约定（issue、triage、domain） |

## 业务与设计

| 文档 | 状态与用途 |
| --- | --- |
| `BUSINESS-QUOTE-FLOW.md` | 现行商机、报价单、订单业务流 |
| `PAGES-V2.md` | 用户逐条定稿的页面规格；代码注释仍按章节引用 |
| `PLANNER-V3.md` | 2026-10-31 技术方案；已实现，保留为设计依据和代码注释引用 |
| `PRODUCT-MODULE.md` | 产品主档与 Excel 下单表设计 |
| `PLAN-menu-dict-align.md` | 菜单对齐和数据字典页的实现任务记录；`static/views/dict.js` 引用 |

## 接口与数据

| 文档 | 用途 |
| --- | --- |
| `EXTERNAL-API.md` | 外部 API 契约、鉴权、幂等和上线验证 |
| `DATABASE-SQLITE-TO-MYSQL.md` | SQLite 数据迁移到 MySQL |
| `DATABASE-MYSQL-BACKUP-RESTORE.md` | MySQL 备份与恢复 |
| `DATABASE-SQLITE-BACKUP-RESTORE.md` | SQLite 备份与恢复 |

## 测试资料

| 文档 | 说明 |
| --- | --- |
| `TC-LEADS.md` / `TC-LEADS.csv` | 线索页手工回归用例，CSV 便于导入表格工具 |
| `gen_lead_testcases.py` | `TC-LEADS.md` / `TC-LEADS.csv` 生成器 |
| `TC-DEALS.md` | 商机页历史测试记录；缺陷多数已在后续提交修复，发布以当前代码和最新回归为准 |

## 归档

`archive/` 保存已被取代或仅剩历史价值的文档。归档内容不再维护，不作为当前实现或验收依据；需要追溯时再查 git 历史。

## 维护约定

- `01-prd.md`、`02-arch.md`、`03-progress.md` 和 `adr/` 采用追加式维护，不删除或重写历史记录。
- 一次性规划、部署记录和已完成任务的临时材料，任务结束后移入 `archive/`；被代码或测试引用的文档不要移动。
- 新增或重命名文档时，同步更新本索引和相关引用，避免留下失效路径。
