本仓库遵循全局 `AGENTS.md`；以下规则仅用于具体化本项目工作流，不放宽全局安全、授权或运行时权限边界。

## Context / CodeGraph

以当前代码、配置、测试和版本化文档为项目事实来源；更具体的目录级规则优先。
有当前 issue / spec 时先读它；否则从用户问题和最相关的 symbol / path 开始。
只围绕当前未决问题扩展上下文；README、package、tests、docs 按需读取。
当前上下文已有充分且未过时的证据时，不做等价重复读取。
当前上下文不足且需要新增代码理解证据时，优先使用 `codegraph explore`；结果充分后不再执行等价的 broad grep / read。
实现时复用现有抽象、接口和依赖方向，不创建平行实现或无关扩展。

## Skill Composition

技能正文要求调用其他 Skill（包括 `Skill tool`）时，优先使用目标项目中实际分发的 Skill，并通过当前运行环境的原生机制加载；没有对应工具时，先读取 `.agents/skills/<name>/SKILL.md` 及当前分支明确要求的引用，再遵循其中指令。
按需加载直接依赖；缺失或不可读时明确报告并停止依赖它的分支，不声称已执行。子 Skill 继承当前权限和项目规则，不扩大授权。

## Validation

优先验证原问题、相关测试和直接受影响模块。
公共 API、共享抽象、跨模块调用链或局部验证不足时扩大验证范围。
项目已有针对当前改动的验证入口时优先使用，不自行创建等价验证流程。

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
