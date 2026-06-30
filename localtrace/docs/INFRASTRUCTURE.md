# LocalTrace Infrastructure

Status: draft for human review.

This document defines engineering infrastructure for the LocalTrace project. These tools support development and review. They are not LocalTrace runtime features unless explicitly listed as runtime dependencies in a later approved spec.

## Infrastructure Goals

- Make specs reviewable as a static site.
- Keep Markdown consistent.
- Keep Python code simple and testable.
- Catch common mistakes before commit.
- Run automated checks on PRs.
- Use an agent to review PRs without letting it modify code.
- Use GitHub issues to prevent untracked work.

## Static Documentation

Recommended tool:

```text
MkDocs + Material
```

Role:

- Build `localtrace/docs` into a navigable local/static site.
- Make specs, architecture, workflow, event schema, and issue rules easy to review.
- Provide stable links from issues and PRs to spec sections.

Planned files:

```text
localtrace/mkdocs.yml
localtrace/docs/*.md
```

Expected commands:

```bash
mkdocs serve
mkdocs build --strict
```

P0 action:

- Define this choice in docs.
- Do not create `mkdocs.yml` until human approves implementation.

## Markdown Lint

Recommended options:

```text
markdownlint-cli2
```

or:

```text
mdformat
```

Recommended first choice:

```text
markdownlint-cli2
```

Role:

- Keep Markdown headings, lists, fenced code, trailing whitespace, and line structure consistent.
- Prevent specs from becoming hard to review.

Expected command:

```bash
markdownlint-cli2 "localtrace/**/*.md"
```

P0 action:

- Document intended linting.
- Add actual config only after spec approval.

## Python Lint And Tests

Recommended tools:

```text
ruff
pytest
pytest-cov optional
```

Role:

- `ruff check`: static checks.
- `ruff format`: formatting.
- `pytest`: behavior tests.
- `pytest-cov`: coverage reporting if useful later.

Expected commands:

```bash
ruff check localtrace
ruff format --check localtrace
pytest localtrace
```

P1 requirement:

- Core skeleton must have pytest tests for config loading, event validation, and event storage.

P2 requirement:

- Winprobe must have tests around event payload construction where possible.

## Pre-Commit Hooks

Recommended tool:

```text
pre-commit
```

Role:

- Run low-cost checks before commit.
- Stop formatting, whitespace, Markdown, and basic Python issues early.

Planned hooks:

```text
ruff check
ruff format
markdownlint
trailing whitespace
end-of-file-fixer
check-yaml
check-json
```

Expected command:

```bash
pre-commit run --all-files
```

P0 action:

- Document intended hooks.
- Add `.pre-commit-config.yaml` only after human approval.

## GitHub Actions

Required workflows after implementation approval:

```text
ci.yml
  - lint
  - tests
  - docs build

pr-agent-review.yml
  - run checks
  - collect diff
  - ask review agent for findings
  - post PR comment

release.yml
  - later phase
  - package artifacts
  - publish GitHub Release
```

P0 CI target:

- Define workflows in docs.
- Do not add YAML until P0 implementation approval.

P1/P0 infrastructure implementation target:

- `ci.yml` runs Markdown lint, docs build, ruff, pytest as soon as corresponding files exist.

## Multi-Channel Distribution

Distribution is defined in P0 and implemented in P6.

Target channels:

1. GitHub Release zip.
2. Windows installer, optional.
3. Browser extension zip.
4. Python package/wheel for development or skill scripts, optional.
5. Docs site artifact or GitHub Pages, optional.

P0 only:

- Document target channels.
- Add placeholder smoke-test concept.

P6:

- Build executable artifacts.
- Package extension.
- Publish GitHub Release.
- Add autostart install/uninstall.

## PR Agent Review

Recommended first mode:

```text
review-only
```

Allowed:

- Read diff.
- Read related specs.
- Produce review findings.
- Comment on PR.

Forbidden:

- Push commits.
- Modify code.
- Merge PR.
- Approve on behalf of human.
- Bypass review gates.

Review checklist:

- Matches issue scope.
- Matches current phase.
- Follows `LOCALTRACE_SPEC.md`.
- Follows `WORKFLOW.md`.
- Does not add auth/token/login.
- Does not add cloud/LAN.
- Does not add derived storage tables.
- Does not add runtime dependencies outside scope.
- Has tests where required.

## Development Process Tools

These tools help the human and coding agents manage the project. They are not
LocalTrace runtime dependencies.

Reference repos:

- Codebase Memory MCP: <https://github.com/deusdata/codebase-memory-mcp>
- Task Master AI: <https://github.com/eyaltoledano/claude-task-master>

Source of truth:

- Repository docs define accepted product and architecture decisions.
- GitHub issues define approved implementation scope.
- Pull requests and CI define review evidence.
- Codebase Memory and Task Master are assistant tools only.

### Codebase Memory

Use:

- At the start of a session, query or refresh project context before proposing
  implementation work.
- Before touching code, inspect relevant modules, prior decisions, and likely
  blast radius.
- After a human accepts a spec decision, record the decision as searchable agent
  memory.
- Before final review, use remembered constraints to check for drift from the
  approved spec.

Allowed memory content:

- Stable architecture decisions.
- Phase boundaries.
- Non-goals.
- Component ownership rules.
- Local-only privacy rules.

Forbidden memory content:

- Secrets.
- Local API credentials.
- Browser profile data.
- Captured LocalTrace event data.
- Temporary guesses that were not accepted by the human.

Authority:

- Codebase Memory can remind the agent about context.
- It cannot replace repository docs.
- It cannot replace GitHub issues.
- It cannot approve implementation.
- It cannot close review gates.

Configuration review:

- MCP/editor configuration is reviewed by the human before use.
- Repo-local files are added only through an approved infrastructure issue.
- User-global MCP configuration is not changed by an agent without separate,
  explicit approval.

Not runtime:

- No LocalTrace binary depends on Codebase Memory.

### Task Master AI

Use:

- After P0 spec approval, parse the approved docs into candidate tasks.
- Break each approved P phase into small task candidates.
- Surface dependency order and likely implementation sequence.
- Help choose the next task candidate.
- Keep a working task board for the agent if useful.

Task rules:

- Task Master output is not the official work ledger.
- Every accepted Task Master task must be mirrored into a GitHub issue.
- GitHub issue scope, non-goals, acceptance checklist, and spec links override
  Task Master text.
- `task-master next` may suggest work, but the agent must select only a
  GitHub issue that is approved for the current phase.
- Task status may be mirrored back to Task Master, but GitHub issue status is
  authoritative.

Forbidden:

- Starting implementation from a Task Master task that has no GitHub issue.
- Expanding scope because Task Master generated extra subtasks.
- Treating Task Master dependency order as human approval.
- Letting Task Master bypass the one-phase-at-a-time rule.

Configuration review:

- Repo-local Task Master files are reviewed before adoption.
- MCP/editor Task Master configuration is reviewed before use.
- AI provider credentials, if any, stay outside LocalTrace runtime files.
- Generated task lists are reviewed by the human before being copied to issues.

Not runtime:

- No LocalTrace process depends on Task Master.

### Playwright

Use:

- Validate Web Settings page after P4.
- Run browser flows.
- Check settings and privacy UI behavior.

Not runtime:

- Playwright is test infrastructure only.

### Firecrawl

Use:

- Research packaging, Windows APIs, or browser-extension constraints.
- Summarize external docs when needed.

Not runtime:

- Firecrawl does not ship with LocalTrace.

### Context7

Use:

- Fetch current library/API docs for implementation.
- Validate usage of selected Python/web libraries.

Not runtime:

- Context7 is not imported by LocalTrace.

## Configuration Review

Infrastructure configuration is implementation work. It needs an issue and human
approval before files are added or changed.

Configuration files expected later:

```text
localtrace/mkdocs.yml
localtrace/.markdownlint-cli2.yaml
localtrace/pyproject.toml
localtrace/.pre-commit-config.yaml
localtrace/.github/workflows/ci.yml
localtrace/.github/workflows/pr-agent-review.yml
localtrace/.github/workflows/release.yml
localtrace/.taskmaster/*
```

Review requirements:

- Explain what the config controls.
- Explain which command or workflow uses it.
- Show the expected local command.
- Show the expected GitHub Actions trigger if applicable.
- State whether it is runtime, test-only, docs-only, or agent-only.
- Confirm it does not add LocalTrace auth, cloud, LAN, or shared runtime
  internals.

## Tool Coordination Workflow

Use this sequence for normal development after P0 spec approval:

1. Docs define the target behavior in `localtrace/docs`.
2. MkDocs serves the docs for human review.
3. Markdown lint keeps docs reviewable.
4. Codebase Memory records accepted decisions after the human approves them.
5. Task Master converts approved docs into candidate task breakdowns.
6. The human reviews generated tasks.
7. Approved tasks are mirrored into GitHub issues.
8. A single GitHub issue is selected for implementation.
9. The agent queries Codebase Memory and reads the linked docs before editing.
10. The agent implements only the approved issue scope.
11. Ruff, pytest, markdownlint, and pre-commit run locally when applicable.
12. GitHub Actions repeats checks on PR.
13. The PR review agent comments with findings only.
14. The human reviews the diff, configuration, and command results.
15. GitHub issue status is updated after human approval.

Ownership summary:

- MkDocs: reviewable docs.
- Markdown lint: readable docs.
- Ruff: Python static checks and formatting.
- Pytest: behavior verification.
- Pre-commit: cheap local gate before commit.
- GitHub Actions: repeatable remote gate on PR/release.
- PR agent review: extra review comments, no authority.
- GitHub issues: official work ledger.
- Codebase Memory: searchable agent context.
- Task Master AI: task breakdown assistant.
- Playwright: Web UI verification after P4.
- Firecrawl: external research assistant.
- Context7: current library documentation lookup.

## Infrastructure Acceptance Checklist

- [ ] Static docs generator choice is clear.
- [ ] Markdown lint choice is clear.
- [ ] Python lint/test stack is clear.
- [ ] Pre-commit role is clear.
- [ ] GitHub Actions workflow roles are clear.
- [ ] PR review agent is review-only.
- [ ] Distribution is P6 implementation, not P0 implementation.
- [ ] Development process tools are not runtime dependencies.
- [ ] Codebase Memory is agent context only, not source of truth.
- [ ] Task Master tasks must be mirrored to GitHub issues.
- [ ] Infrastructure config files require human review before adoption.
- [ ] Tool coordination workflow is explicit.
