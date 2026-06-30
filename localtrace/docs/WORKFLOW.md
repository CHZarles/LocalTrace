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
- Linked spec section.
- Human approval to implement.

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
- Propose architecture.

### After Implementation

Every implementation task completion must include:

- Changed files.
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
- Does this change introduce any forbidden feature?
- Does this change require new runtime dependencies?
- Does the human explicitly approve implementation?

After implementation:

- Did the changed files match the issue scope?
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

Every implementation PR or commit must reference a small issue. The issue must be under a phase tracking issue.

## Tool-Assisted Workflow

Development tools can reduce drift, but they do not change authority.

Required order:

1. Human-approved docs define the phase.
2. Task Master may generate candidate tasks from approved docs.
3. Human reviews task candidates.
4. Approved task candidates are copied into GitHub issues.
5. GitHub issues become the official work ledger.
6. Codebase Memory is queried before implementation to recover relevant
   decisions and constraints.
7. Implementation follows exactly one approved GitHub issue.
8. Pre-commit and local checks run when applicable.
9. GitHub Actions repeats checks on PR.
10. PR agent review comments on risks, but does not approve.
11. Human reviews the diff, configuration, and command results.

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
- [ ] Issue is required for each change.
- [ ] One phase at a time.
- [ ] Agent review cannot replace human review.
- [ ] CI green cannot replace human review.
- [ ] No auth rule is explicit.
- [ ] Local HTTP JSON seam rule is explicit.
- [ ] Task Master cannot replace GitHub issues.
- [ ] Codebase Memory cannot replace repository docs.
- [ ] Infrastructure configuration requires human review.
