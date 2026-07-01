# WorkTrace 开发流程

状态：开发执行规则。

本文档定义 WorkTrace 的日常开发流程：

```text
issue -> branch -> code -> tests -> PR -> review -> merge
```

目标是让每次改动都有明确范围、独立分支、本地验证、可审阅 PR 和清楚的合并记录。

## 权威顺序

开发时按这个顺序判断：

1. 仓库文档定义产品、架构和流程决策。
2. GitHub issue 定义已经批准的实现范围。
3. Branch 承载某一个 issue 的实现。
4. Pull request 汇总 diff、测试证据、review 和 merge 决策。
5. Codex 工具提供上下文、拆解、实现和检查证据。

Codex 工具辅助开发。GitHub issue 和 PR review 决定一项实现工作是否可以开始、是否可以完成。

## 工具职责

### CodeGraph

CodeGraph 用来理解代码结构和影响面。

使用时机：

1. 写 issue 前，受影响代码区域还不清楚时。
2. 写代码前，确认相关模块、入口、依赖和影响范围。
3. 实现过程中，改动跨模块、跨运行时、跨 UI/API 边界时。
4. 开 PR 前，检查 diff 是否只触碰了预期组件。
5. Review 期间，回答 reviewer 对影响面的追问。

产出内容：

- 相关文件和模块。
- 调用路径或依赖关系。
- 受影响的运行时入口、API、UI、配置或数据结构。
- 可以复制到 issue 或 PR 的风险说明。

### Task Manager

Task Manager 用来拆解已经批准的工作，并跟踪执行状态。

使用时机：

1. 相关需求、spec 或设计文档已经批准后。
2. 创建小 issue 前，生成候选任务和依赖顺序。
3. 实现过程中，跟踪当前 issue 内部的子任务。
4. PR review 或 merge 后，同步最终状态。

Task Manager 的任务只有复制进 GitHub issue，并补齐 scope、acceptance、verification 后，才进入实现流程。

推荐状态映射：

| Task Manager 状态 | GitHub 状态 |
| --- | --- |
| Backlog | 候选任务，还未进入实现 |
| Ready | GitHub issue 已存在并已批准 |
| In Progress | Branch 已创建，正在实现 |
| Review | PR 已打开 |
| Done | PR 已合并，issue 已关闭 |

### Codex Agent

Codex Agent 用来实现代码、运行本地验证、准备 PR、处理 review 修改。

给 Codex 开始实现前，需要提供：

- GitHub issue 编号。
- 分支名，或让 Codex 按规则创建分支。
- 关联文档或 spec 章节。
- Acceptance checklist。
- 预期验证命令。

Codex 完成后需要给出：

- 改动文件列表。
- 关键实现说明。
- 验证命令和结果。
- PR summary。
- Review 修改说明。

### PR Review Agent

PR Review Agent 在 PR 创建后使用。

产出内容：

- 带文件和行号的 findings。
- scope、测试、回归和维护性风险。
- 需要人工 reviewer 判断的问题。

PR Review Agent 提供 review 证据。人工 review 决定是否 merge。

## 标准流程

### 1. Issue

每个实现改动先从 GitHub issue 开始。

Issue 需要写清楚：

- 问题是什么。
- 对用户或开发者的影响是什么。
- 本次 scope 是什么。
- 本次 issue 的边界是什么。
- Acceptance checklist。
- Verification plan。
- 相关 docs、spec、设计或历史决策链接。
- CodeGraph notes，适用于影响范围还不清楚的改动。
- Task Manager link 或 task ID，适用于从任务拆解生成的 issue。

一个 issue 对应一个可 review 的改动。Checklist 混入多个无关组件、无关风险或无关测试路径时，需要拆成多个 issue。

Issue 模板：

````markdown
# Short Title

## Problem

## Impact

## Scope

## Boundaries

This issue only covers:

- ...

Future or separate issues cover:

- ...

## Acceptance Checklist

- [ ] ...

## Verification

Expected commands:

```bash
...
```

## References

- Spec:
- CodeGraph notes:
- Task Manager:

## Review Gate

Implementation starts after human approval.
````

进入下一步前确认：

- Issue 有明确 acceptance checklist。
- Issue 有 verification plan。
- 人工已经批准开始实现。

### 2. Branch

Issue 批准后创建 branch。

分支命名：

```text
<type>/<issue-number>-<short-title>
```

示例：

```text
docs/123-development-workflow
fix/124-update-retry-startup
feat/125-report-export-settings
chore/126-localtrace-ci
```

Branch 需要做到：

- 从当前 main 分支切出。
- 一个 branch 绑定一个 issue。
- commit message 在合适时引用 issue。

Commit 示例：

```text
docs(workflow): add development workflow guide
fix(update): wait for updater process startup
feat(reports): add export settings panel
```

### 3. Code

编辑前需要做：

1. 读 issue 和关联文档。
2. 影响区域不明确时先用 CodeGraph。
3. 找到满足 acceptance checklist 的最小文件集合。
4. 如果该 issue 在 Task Manager 里跟踪，把状态改到 `In Progress`。

编辑过程中需要做：

- 按批准的 issue scope 实现。
- 把无关格式化、无关重命名、无关依赖变化和无关生成文件留到单独 issue。
- 行为、命令或流程变化时同步文档。
- 按风险级别补测试或验证。
- 发现新增工作时，先更新 issue 或创建 follow-up issue，再实现新增范围。

Code 完成标准：

- Acceptance checklist 已实现。
- 改动文件符合 issue scope。
- 文档反映新的行为或流程。
- 测试或验证覆盖了改动行为。

### 4. Tests

开 PR 前运行相关本地检查。

按改动区域选择命令：

- Rust core 或 collector:
  `cargo fmt --check`, `cargo test`
- Rust lint 敏感改动:
  `cargo clippy --all-targets --all-features -- -D warnings`
- Flutter UI:
  `flutter analyze`, `flutter test`
- Browser extension:
  Chrome/Edge 手动加载、extension console 检查、`/health` 或 event smoke test
- LocalTrace docs:
  `npm --prefix localtrace run lint:md`
  `mkdocs build --strict -f localtrace/mkdocs.yml`
- Repo hooks:
  `pre-commit run --all-files`
- Windows packaging:
  `powershell -ExecutionPolicy Bypass -File dev/package-windows.ps1 -Installer`

Verification notes 需要记录：

- 精确命令。
- 通过或失败结果。
- 关键输出摘要。
- 跳过的命令、原因和替代验证方式。

进入下一步前确认：

- 必要本地检查已通过。
- 已知验证缺口写进 PR。
- UI 改动有截图或明确的视觉验证说明。

### 5. PR

本地验证后打开 PR。

PR 需要包含：

- 关联一个 issue；范围更大时需要人工提前批准。
- 使用 `Fixes #<issue-number>` 或 `Closes #<issue-number>` 关闭对应 issue。
- 改动摘要。
- 验证命令和结果。
- UI 改动截图。
- 生成文件变化说明。
- 跨模块改动的 CodeGraph 影响说明。
- Task Manager 状态同步到 `Review`，适用于被跟踪的 issue。

PR 模板：

```markdown
## Summary

- ...

## Issue

Fixes #...

## Scope Check

- Issue scope:
- Changed areas:
- CodeGraph impact notes:

## Verification

- [ ] `command` - result

## UI Evidence

Screenshots or visual notes:

## Risk Notes

- ...
```

进入 review 前确认：

- PR 描述说明改了什么、怎么验证。
- CI 已启动或已完成。
- Reviewer 能从 diff 对回 issue acceptance checklist。

### 6. Review

Review 用来确认 scope、行为、测试和可维护性。

Review 顺序：

1. CI 运行。
2. PR Review Agent 运行，适用于已配置的仓库。
3. 人工 reviewer 检查 diff、行为和验证证据。
4. Codex Agent 在同一分支处理 review comments。
5. Review 修改后重新运行相关测试。
6. PR 描述补齐最终验证结果。

Review checklist：

- Diff 符合 issue scope。
- Acceptance checklist 已完成。
- 测试覆盖改动行为。
- CI 通过。
- Review comments 已解决。
- 人工 approval 已记录。

### 7. Merge

Approval 和检查通过后 merge。

Merge 前确认：

- PR 已获得人工 approval。
- CI 通过，或 PR 写明已接受的例外。
- PR 带 issue closure keyword。
- 用户可见变化已经更新 release notes。
- Task Manager 在 merge 后同步到 `Done`，适用于被跟踪的 issue。
- 合并后删除不再需要的 branch。

Merge 后需要做：

- 确认 issue 已关闭，或已写明剩余 follow-up。
- 对 review 中发现的延期工作创建 follow-up issue。
- 持久架构或流程决策写回仓库文档。
- follow-up 影响面不清楚时继续用 CodeGraph。

## 小改动快路径

小修也走同一条链路，只缩短材料：

```text
short issue -> small branch -> focused diff -> relevant test
-> PR -> review -> merge
```

短 issue 仍然需要：

- Problem。
- Scope。
- Acceptance。
- Verification。

## 文档改动

文档改动在这些情况也需要 issue 和 PR：

- 改开发流程。
- 改架构决策。
- 改产品行为。
- 改发布流程。
- 改贡献者指导。

最小验证：

- 格式重要时检查 Markdown 渲染结果。
- 路径被 lint config 覆盖时运行 Markdown lint。
- 检查本地文件链接。

## 工具使用时机表

| 阶段 | CodeGraph | Task Manager | Codex Agent | GitHub |
| --- | --- | --- | --- | --- |
| Intake | 影响区域不清楚时看代码图 | 记录候选任务 | 总结需求 | 起草 issue |
| Issue | 补影响说明 | 关联已接受任务 | 起草 scope 和 acceptance | 批准 issue |
| Branch | 确认目标模块 | 标记 ready/in progress | 创建 branch | 从 main 切分支 |
| Code | 查依赖和调用路径 | 跟踪子任务 | 编辑文件 | commit 到 branch |
| Tests | 确认受影响 surface | 跟踪验证任务 | 运行命令并修复失败 | 准备 PR 证据 |
| PR | 总结影响面 | 标记 review | 写 PR 描述 | 打开 PR |
| Review | 回答影响面问题 | 跟踪 review fixes | 处理 review 修改 | 人工 review 和 CI |
| Merge | 支持 follow-up 分析 | 标记 done | 总结最终状态 | merge 并关闭 issue |

## Codex Prompt 模板

分配实现任务给 Codex 时使用：

```text
Work on GitHub issue #<number>.
Create or use branch <type>/<issue-number>-<short-title>.
Read the linked docs and acceptance checklist first.
Use CodeGraph before editing if the affected modules are unclear.
Implement only this issue scope.
Run the relevant verification commands.
Prepare a PR summary with changed files, tests, risks, and Fixes #<number>.
Update Task Manager state if this issue is tracked there.
```

## Definition Of Done

一项改动完成时必须满足：

- Linked issue scope 已实现。
- Acceptance checklist 已完成。
- Local verification 已运行。
- CI 已通过，或 PR 记录了已接受的例外。
- PR review 已完成。
- 人工 approval 已记录。
- PR 已 merge。
- Issue 已关闭，或已写明剩余 follow-up。
