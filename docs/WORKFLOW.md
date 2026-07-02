# LocalTrace Workflow

Status: draft for human review.

This workflow exists to prevent vibe-coding drift. The project may still be built with AI assistance, but each phase is controlled by explicit spec, issue, acceptance, and human review gates.

## Hard Rule

No implementation code is written until the current phase spec and acceptance checklist are reviewed and explicitly approved by the human.

Approval words must be clear:

```text
approved
通过
批准实现
进入实现
```

Ambiguous replies do not count.

## Human Review Gates

### Before Implementation

Every implementation task must have:

- GitHub issue.
- Scope.
- Non-goals.
- Acceptance checklist.
- Implementation plan.
- Linked spec section.
- Human approval to implement.

Non-trivial implementation issues must include a PlantUML implementation plan
before coding starts. Tiny fixes may use a short text plan instead.

Forbidden before approval:

- Python implementation files.
- JavaScript extension implementation files.
- Web UI implementation files.
- Skill scripts.
- CI YAML.
- `pyproject.toml`.
- `.pre-commit-config.yaml`.
- Packaging scripts.

Allowed before approval:

- Read existing code.
- Write or update spec documents.
- Write issue descriptions.
- Write acceptance checklists.
- Write PlantUML implementation plans in GitHub issues.
- Propose architecture.

### After Implementation

Every implementation task completion must include:

- Changed files.
- Planned implementation versus actual diff.
- Deviation notes when actual flow differs materially from the issue plan.
- Commands run.
- Command results.
- Any skipped verification and why.
- Human review of diff or behavior.
- Explicit human approval to move forward.

CI green is required but not sufficient. Agent review is required but not sufficient. Human review is always required.

## Phase Discipline

Only one P phase is active at a time.

Phases:

```text
P0 Spec + Infrastructure Freeze
P1 Core Skeleton
P2 Winprobe
P3 Browser Extension
P4 Web Settings
P5 Skill
P6 Packaging / Autostart
```

Rules:

- Do not implement future phase features.
- Do not prepare hidden future abstractions.
- Do not add runtime dependencies for future phases.
- Do not expand capture scope without a new approved spec.

## Scope Control

Every issue must explicitly list non-goals.

Examples:

```text
P1 Core Skeleton non-goals:
- Winprobe implementation.
- Browser extension implementation.
- Web UI.
- Skill scripts.
- Packaging.
- Timeline/top derived API.
```

If work reveals a new need, create or update an issue. Do not silently implement it.

## Review Questions The Agent Must Ask

Before implementation:

- Does this issue match the current phase?
- Is the acceptance checklist specific enough to test?
- Does a non-trivial implementation issue have a PlantUML plan in the issue?
- Does this change introduce any forbidden feature?
- Does this change require new runtime dependencies?
- Does the human explicitly approve implementation?

After implementation:

- Did the changed files match the issue scope?
- Did the actual diff match the implementation plan, or are deviations recorded?
- Did tests/lints/docs build run?
- Did any generated or unrelated file change?
- Did the work introduce auth, cloud, LAN, or derived tables?
- Is the human ready to approve moving forward?

## No Auth Rule

LocalTrace never implements:

- Login.
- Token.
- API key.
- Account.
- Cloud authentication.
- Extension pairing token.

Security is based on:

- Fixed loopback host.
- No LAN.
- No cloud.
- Privacy filtering.
- Local-only storage.

Any PR that adds auth/login/token behavior violates the spec.

## No Shared Internals Rule

Runtime parts communicate through local HTTP JSON only.

Forbidden:

- Skill imports LocalTrace Python internals.
- Web UI reads SQLite.
- Probe writes SQLite.
- Extension reads SQLite.
- Shared business-code package used by multiple runtime parts.

## Issue Required Rule

No issue, no implementation.

Every implementation PR or commit must reference an approved GitHub issue.

A phase may be tracked by one active issue when the work is coherent and
reviewable. Do not create child issues unless the human explicitly asks to split
the phase.

## Small-Step Development Rule

Default cadence:

```text
one approved issue -> one branch -> focused commits
-> one PR -> review -> merge -> next issue
```

Hard rules:

- One PR solves one clear target.
- One branch is bound to one issue by default.
- Do not keep adding later phases to a long-lived aggregate branch.
- Do not mix unrelated docs, CI, infrastructure, and runtime behavior in one PR.
- After a PR merges, start the next issue from `main`.
- Non-trivial implementation issues need a PlantUML implementation plan before
  coding starts.
- PRs must compare planned implementation against the actual diff.
- Review Agent runs only after a PR exists; it is not pre-implementation approval.
- Task Manager is only used when coordination complexity justifies it.
- CodeGraph or another context check runs before unfamiliar code, API, schema,
  runtime, privacy, or security changes.
- Python development environments are created inside the repository, for example
  `.venv`.
- Local Python environments are never committed to git.
- Commits written by Codex use the `Codex Agent` git author, not the human
  developer name.
- GitHub PR author is determined by the account that creates the PR, not by git
  commit author.
- If Codex creates a PR with a human GitHub login, that human is the PR author.
- A PR author cannot approve their own PR.
- If the repository has an independent reviewer, human approval must come from a
  reviewer who is not the PR author.
- In a solo repository, the PR author cannot use GitHub Approve; owner merge is
  the human review and merge authorization record.

PR size targets:

- Documentation PRs should stay under 300 changed lines when practical.
- Normal code PRs should stay under 500 changed lines when practical.
- If a PR grows past the target, evaluate scope split before adding more code.

A phase may still use one issue only when:

- The checklist remains reviewable.
- The diff remains focused on one target.
- Each PR can still merge independently.

If a phase issue becomes too large:

- Do not auto-create many child issues.
- Ask the human whether to split the scope.
- Each split issue uses its own branch, PR, review, and merge.

## Tool Policy

Development tools can reduce drift, but they do not define authority.

Source of truth:

- Repository docs define accepted product and architecture decisions.
- GitHub issues define approved implementation scope.
- Pull requests define reviewable change sets.
- Human review defines approval.

Tool output cannot expand scope, approve work, close issues, or merge PRs.

### Task Manager

Task Manager is optional.

Use it when work has multiple parallel tracks, multiple agents, unclear
sequencing, or a checklist that has become too large for one issue.

Do not use Task Manager as a mandatory step for every issue.

Task Manager must not:

- Replace GitHub issues.
- Create GitHub child issues unless explicitly requested.
- Expand scope beyond the approved issue.
- Close GitHub issues.
- Override human review.

### Context Check

A context check is required before implementation when work touches unfamiliar
code, migrates behavior from old code, crosses module boundaries, or may affect
public interfaces, storage schema, runtime behavior, privacy, or security.

The context check may use CodeGraph, repository search, docs, or manual code
reading.

If the context check changes risk, scope, or implementation direction, summarize
it in the issue or PR.

### Implementation Plan

The implementation plan is a review artifact, not a source of extra scope.

For every non-trivial implementation issue, the agent must post a compact
PlantUML plan in the GitHub issue before writing implementation code. The plan
must show the intended modules or files, the API/runtime/data flow, the
verification flow, expected changed files, acceptance checklist mapping, and
explicit non-goals where useful.

The plan may be updated before coding starts or when the issue scope is
explicitly revised. After coding starts, material differences from the plan must
be recorded as plan deviation notes in the issue or PR, and the agent must
confirm that the deviation remains inside the approved issue scope.

Tiny fixes may use a short text plan instead of PlantUML. Examples include
typos, wording-only docs updates, single-line config corrections, issue or PR
metadata updates, and mechanical lint fixes inside an already approved scope.

### Review Agent

Review Agent runs after a PR exists and has a reviewable diff.

Review Agent is advisory only. It may produce findings and questions, but it
cannot approve, merge, close issues, or override human review.

If automated Review Agent is not configured, manual agent review may be used.
Human review remains required.

Forbidden shortcuts:

- Implementing directly from a Task Master task.
- Treating Codebase Memory as a spec.
- Treating PR agent review as human approval.
- Treating CI green as human approval.
- Adding infrastructure configuration without issue review.

## Verification Baseline

Expected checks once infrastructure exists:

```text
ruff check
ruff format --check
pytest
markdownlint
mkdocs build
pre-commit run --all-files
```

Not every phase has all checks at first. `INFRASTRUCTURE.md` defines when each check becomes required.

## Workflow Acceptance Checklist

- [ ] Human approval is required before implementation.
- [ ] Human approval is required after implementation.
- [ ] PR author approval does not count; solo repo owner merge counts as review.
- [ ] Issue is required for each change.
- [ ] One phase at a time.
- [ ] A coherent phase may use one active issue.
- [ ] Agent review cannot replace human review.
- [ ] CI green cannot replace human review.
- [ ] No auth rule is explicit.
- [ ] Local HTTP JSON seam rule is explicit.
- [ ] Task Master cannot replace GitHub issues.
- [ ] Task Master is optional, not mandatory for every issue.
- [ ] Codebase Memory cannot replace repository docs.
- [ ] Infrastructure configuration requires human review.
