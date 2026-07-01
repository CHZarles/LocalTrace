# LocalTrace Architecture

Status: draft for human review.

This document defines module placement and interfaces. It uses the words Module, Interface, Seam, Adapter, and Implementation intentionally.

## Runtime Architecture

```text
localtrace-winprobe.exe
  -> POST /events
       |
       v
localtrace.exe
  -> privacy rules
  -> SQLite raw events
  -> local HTTP JSON
       ^
       |
browser extension

web settings UI
  -> local HTTP JSON

localtrace-skill scripts
  -> local HTTP JSON
```

## Modules

### LocalTrace Core

Role:

- Own raw event ingest.
- Own privacy filtering.
- Own config file.
- Own SQLite writes.
- Own local HTTP JSON interface.
- Own probe lifecycle supervision.

Interface:

- Local HTTP JSON endpoints.
- `config.json`.
- Process exit code and logs.

Implementation:

- Python HTTP server.
- SQLite.
- JSON config.

Core is the only Module allowed to write LocalTrace SQLite.

### Windows Probe

Role:

- Capture Windows app activity.
- Capture app audio activity.
- Apply idle gating before sending foreground activity.
- Send raw events to core.

Interface:

- Command-line args or environment for endpoint/flags.
- Local HTTP `POST /events`.
- Logs.

Implementation:

- Python first.
- Use `ctypes` or `pywin32` if enough.
- Use a thin C++ helper only if Python access is unreliable.

The probe has no storage adapter.

### Browser Extension

Role:

- Capture browser tab/domain activity.
- Capture background audio tab activity.
- Send raw events to core.

Interface:

- Browser extension settings popup.
- Local HTTP `POST /events`.

Implementation:

- Chrome/Edge Manifest V3.
- `fetch` to localhost.
- Offscreen/keep-alive mechanism may be reused from current extension.

Native Messaging is out of scope for v1.

### Web Settings UI

Role:

- Configure LocalTrace.
- Manage privacy rules.
- Show health diagnostics.

Interface:

- Local HTTP JSON endpoints.

Implementation:

- Frontend technology is not fixed.
- It may be server-rendered HTML, static HTML/JS, or a small SPA.
- It must not read SQLite directly.

### LocalTrace Skill

Role:

- Give Codex/agents access to captured raw events.
- Compute summaries and diagnostics on demand.

Interface:

- Skill scripts.
- Local HTTP JSON endpoints.

Implementation:

- Python scripts under a skill directory.
- No import of LocalTrace internal modules.
- No direct SQLite access.

MCP can be added later as an adapter over the same local HTTP interface.

## Stable Seams

The primary seam is:

```text
Local HTTP JSON API
```

Every other runtime part crosses that seam.

Allowed adapters:

- Windows probe HTTP adapter.
- Browser extension HTTP adapter.
- Web UI HTTP adapter.
- Skill HTTP adapter.
- Future MCP HTTP adapter.

Forbidden seams:

- Direct SQLite access from external components.
- Shared business-code package imported by multiple runtime components.
- Private Python module imports from skills.

## Data Ownership

```text
localtrace.exe owns:
  config.json
  localtrace.db
  privacy rules
  tracking pause state

winprobe owns:
  current polling loop state
  last sent app/audio state
  idle gating state

browser extension owns:
  browser local/sync extension settings
  last tab/audio state

skill owns:
  temporary analysis calculations
```

## Process Model

LocalTrace runs in the current user session.

Not a Windows Service:

- The system needs access to current user session activity.
- Service/session 0 would make foreground window capture harder.
- User-session background process is easier to debug and replace.

Process set:

```text
localtrace.exe
localtrace-winprobe.exe
browser extension service worker/offscreen document
browser process showing Web UI when opened
```

## Startup

V1 autostart target:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

Alternative:

```text
Task Scheduler at user logon
```

Windows Service is not allowed in v1.

## Naming

System:

```text
LocalTrace
```

Process names:

```text
localtrace.exe
localtrace-winprobe.exe
```

Data:

```text
%LOCALAPPDATA%\LocalTrace\config.json
%LOCALAPPDATA%\LocalTrace\localtrace.db
```

Extension:

```text
LocalTrace Extension
```

Skill:

```text
localtrace-skill
```

## Old WorkTrace Code Reuse

Old code is a reference, not the new architecture.

May reuse ideas or small code sections from:

- `collectors/windows_collector/src/main.rs`
- `extension/`
- current UI information architecture

Must not preserve:

- Flutter client as core runtime.
- Reports/Planner/Review model.
- Derived block/timeline storage.
- Old endpoint compatibility unless explicitly specified.

## First Directory Draft

```text
localtrace/
  docs/
    LOCALTRACE_SPEC.md
    ARCHITECTURE.md
    EVENT_SCHEMA.md
    WORKFLOW.md
    INFRASTRUCTURE.md
    ISSUES.md
  apps/
    localtrace/
    winprobe/
  extension/
  web/
  skill/
```

Only `docs/` exists during P0 spec review. Other directories are created only after approval.

## Architecture Acceptance Checklist

- [ ] Each runtime component has a single clear role.
- [ ] Local HTTP JSON is the only runtime interface between components.
- [ ] SQLite is owned only by `localtrace.exe`.
- [ ] No token/login/auth/LAN/cloud path exists.
- [ ] Winprobe is independent from core.
- [ ] Browser extension stays MV3 + localhost fetch.
- [ ] Skill does not import core internals.
