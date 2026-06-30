# LocalTrace Issue Workflow

Status: draft for human review.

LocalTrace uses GitHub issues to control every implementation change. This is mandatory because the project is intentionally built with AI assistance and must avoid uncontrolled scope drift.

## Issue Structure

Use one tracking issue per phase:

```text
P0 Spec + Infrastructure Freeze
P1 Core Skeleton
P2 Winprobe
P3 Browser Extension
P4 Web Settings
P5 Skill
P6 Packaging / Autostart
```

Use small implementation issues under each tracking issue.

Example P0 issues:

```text
P0-001 Write LOCALTRACE_SPEC.md
P0-002 Write EVENT_SCHEMA.md
P0-003 Write ARCHITECTURE.md
P0-004 Write WORKFLOW.md
P0-005 Write INFRASTRUCTURE.md
P0-006 Write issue workflow docs
P0-007 Set up MkDocs
P0-008 Set up markdown lint
P0-009 Set up ruff/pytest
P0-010 Set up pre-commit
P0-011 Set up CI lint/test/docs
P0-012 Set up PR agent review workflow
```

P0 documentation issues may be completed before implementation approval. P0 infrastructure implementation issues require explicit human approval.

## Tracking Issue Template

```markdown
# Pn Phase Name

## Scope

## Non-Goals

## Dependencies

## Issues

- [ ] Pn-001 ...
- [ ] Pn-002 ...

## Acceptance Checklist

- [ ] ...

## Review Gate

Implementation can start only after explicit human approval.
Phase can close only after human review of results.
```

## Small Issue Template

```markdown
# Pn-XXX Short Title

## Scope

## Non-Goals

## Spec Links

## Acceptance Checklist

- [ ] ...

## Verification

Commands expected:

```bash
...
```

## Review Gate

No implementation until human approval.
```

## Required Fields

Every small issue must have:

- Scope.
- Non-goals.
- Acceptance checklist.
- Spec links.
- Verification plan.
- Review gate.

## PR Rules

Every PR must:

- Link exactly one small issue unless explicitly approved.
- Include changed files.
- Include verification commands and results.
- Include screenshots only if UI changed.
- Include agent review output if configured.
- State whether any generated files changed.

Every PR must not:

- Include unrelated formatting churn.
- Implement future phase work.
- Add auth/token/login.
- Add LAN/cloud behavior.
- Add derived tables without approved spec.
- Modify runtime capture scope without approved spec.

## Commit Rules

Preferred commit style:

```text
docs(localtrace): write p0 spec draft
feat(localtrace-core): add health endpoint
test(localtrace-core): cover event validation
chore(localtrace): add markdown lint
```

Each commit should reference the issue when practical:

```text
Refs #123
Closes #123
```

## Labels

Recommended labels:

```text
phase:p0
phase:p1
phase:p2
phase:p3
phase:p4
phase:p5
phase:p6

type:spec
type:implementation
type:test
type:infra
type:docs
type:review

status:blocked
status:ready-for-review
status:approved
```

## Agent Review In Issues

Agent-generated plans must be posted or summarized in the relevant issue before implementation.

Agent review cannot close issues. Only the human can accept completion.

## Task Master Relationship

Task Master AI may generate task candidates, dependency order, and next-task
suggestions. It is not the official project ledger.

Rules:

- A Task Master task becomes actionable only after it is copied into a GitHub
  issue.
- The GitHub issue must use the normal small issue template.
- The GitHub issue must link the relevant spec sections.
- The GitHub issue must list non-goals even if Task Master did not.
- The GitHub issue acceptance checklist overrides Task Master text.
- Task Master status may mirror GitHub issue status, not the other way around.

Forbidden:

- Starting implementation from a Task Master task without a GitHub issue.
- Closing a GitHub issue because Task Master says the task is done.
- Adding Task Master-generated extra scope without human issue review.

## Done Definition

An implementation issue is done only when:

- Scope is implemented.
- Non-goals were not implemented.
- Acceptance checklist is complete.
- Verification commands ran.
- CI is green, once CI exists.
- PR agent review ran, once configured.
- Human explicitly approved.

## Issue Workflow Acceptance Checklist

- [ ] Every implementation change requires an issue.
- [ ] Phase tracking issues are required.
- [ ] Small issues have acceptance checklists.
- [ ] Issues define non-goals.
- [ ] Human approval is required to close implementation issues.
- [ ] Agent review cannot replace human review.
- [ ] Task Master tasks must be mirrored into GitHub issues.
- [ ] GitHub issue status is authoritative.
