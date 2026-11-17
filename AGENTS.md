本仓库遵循全局 `AGENTS.md`；以下规则仅用于具体化本项目工作流，不放宽全局安全、授权或运行时权限边界。

## Context / CodeGraph

以当前代码、配置、测试和版本化文档为项目事实来源；更具体的目录级规则优先。
有当前 issue / spec 时先读它；否则从用户问题和最相关的 symbol / path 开始。
只围绕当前未决问题扩展上下文；README、package、tests、docs 按需读取。
当前上下文已有充分且未过时的证据时，不做等价重复读取。
当前上下文不足且需要新增代码理解证据时，优先使用 `codegraph explore`；结果充分后不再执行等价的 broad grep / read。
实现时复用现有抽象、接口和依赖方向，不创建平行实现或无关扩展。

## 项目文档

`docs/` 下三份文档是项目事实来源，按当前任务需要读取：

| 文件 | 作用 | 变更时机 |
|---|---|---|
| `docs/01-prd.md` | 产品需求：做什么、为什么做、验收标准 | 需求新增/变更/砍掉时 |
| `docs/02-arch.md` | 软件架构：怎么实现、模块边界、技术决策 | 结构、依赖、接口、数据模型变化时 |
| `docs/03-progress.md` | 当前进度：做到哪了、下一步做什么 | 每个任务结束后必须更新 |

开工前：开发任务先看 `03-progress.md` 的当前状态与阻塞项；涉及需求或验收时在 `01-prd.md` 定位需求 ID；涉及结构、接口或数据模型时读 `02-arch.md`。需求文档中找不到对应条目时先提问，不自行发明需求。

收工后：

1. 更新 `03-progress.md`（必做）：变更日志最上方追加一条，更新任务状态，记录遗留问题与下一步。
2. 更新 `02-arch.md`（仅结构性变化）：新增模块/依赖/接口/数据表时更新对应章节；非显然的技术选择追加到「决策记录」，写清背景与取舍。
3. 更新 `01-prd.md`（仅需求真的变了）：只做追加与状态变更，删除历史需标注理由；变更来源标记 `[用户明确要求]` / `[实现中发现约束]`。

文档规则：

- 文档是追加式的，禁止删除或重写历史记录；过时内容标 ~~废弃~~ 并说明原因。
- 状态标记统一用 `📋 待办` / `🚧 进行中` / `✅ 已完成` / `⛔ 阻塞` / `🗑️ 已取消`。
- 需求、任务、决策使用 ID（`REQ-001` / `TASK-012` / `ADR-003`），有对应 issue 或任务时在提交信息中引用。
- 文档里的「最后更新」日期随改动刷新。
- 不允许出现「代码改了但进度文档没动」。

## Skill Composition

技能正文要求调用其他 Skill（包括 `Skill tool`）时，优先使用目标项目中实际分发的 Skill，并通过当前运行环境的原生机制加载；没有对应工具时，先读取 `.agents/skills/<name>/SKILL.md` 及当前分支明确要求的引用，再遵循其中指令。
按需加载直接依赖；缺失或不可读时明确报告并停止依赖它的分支，不声称已执行。子 Skill 继承当前权限和项目规则，不扩大授权。

## Validation

优先验证原问题、相关测试和直接受影响模块。
公共 API、共享抽象、跨模块调用链或局部验证不足时扩大验证范围。
项目已有针对当前改动的验证入口时优先使用，不自行创建等价验证流程。
改动必须补充或更新相关测试，交付前确保相关测试与验证通过。
改动后端代码后重启后端服务，确认能正常启动再继续验证或交付。

## 数据库规则

- 每个业务表必须有 `create_time`、`update_time`、`is_delete` 字段。
- `is_delete`：`0` 表示正常，`1` 表示已删除；查询默认过滤 `is_delete = 0`。
- 不建数据库外键，引用一致性由业务层维护。

## Git

每个独立 issue / spec 对应一个交付 commit，不按实现、测试、review 等阶段拆分。
仅在本次任务完成并通过相关验证后 commit；明确要求 checkpoint 时可提交未完成状态，并注明未完成或未通过的验证。
commit 前检查 `git diff` 和 `git status`；只 stage 当前任务改动，不混入其他任务或用户已有修改。
commit 不授权 push、发布或其他远程写入。
commit 后报告 hash，以及本次执行的主要验证及结果。

## Completion

完成时简要说明结果、关键修改和验证。
存在重要未验证项、已知限制、既有失败或剩余风险时明确指出。
有 commit 时报告 commit hash。

## Agent skills

### Issue tracker

GitHub Issues in `mling17/sunshine-crm`; operate through `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles keep the default label names. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.
