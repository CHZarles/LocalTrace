# LocalTrace Spec

Status: draft for human review.

LocalTrace is a local-only activity capture system for one Windows user session. It uses a small background process, an independent Windows probe, a browser extension, a local Web UI, and a skill-facing HTTP surface.

No implementation code may be written from this spec until the human review gate in `WORKFLOW.md` is passed.

## Goals

- Run as a user-session background application on Windows.
- Keep all captured data local.
- Preserve the capture signals already adopted by LocalTrace.
- Store raw events only.
- Expose raw data through a local HTTP JSON interface.
- Let agent skills compute timeline/top/day summaries on demand.
- Keep each runtime part independently understandable and replaceable.
- Avoid shared business code between runtime parts.
- Provide a minimal Web UI for settings, privacy, and health checks.

## Non-Goals

LocalTrace v1 does not include:

- Separate foreground desktop client.
- Task planning UI.
- TODO.
- Report UI.
- Daily/weekly report generation.
- LLM prompt configuration.
- Review notes.
- Block review workflow.
- Review reminders.
- Derived `blocks`, `timeline_segments`, or `top_items` tables.
- Cloud sync.
- Account system.
- Login.
- Token, API key, or auth layer.
- LAN access.
- Windows Service.
- Native Messaging for the browser extension.
- Screenshot, keyboard logging, web page body capture, or default full URL capture.
- Runtime dependency on Codebase Memory, Task Master, Firecrawl, Context7, or Playwright.

## Product Shape

LocalTrace v1 consists of four deliverables:

1. `localtrace.exe`
   - User-session background process.
   - No main desktop window.
   - Owns local HTTP API.
   - Owns SQLite data writes.
   - Owns `config.json` read/write.
   - Owns privacy rule application.
   - Hosts or opens the local Web settings page.
   - Starts, stops, and health-checks `localtrace-winprobe.exe`.

2. `localtrace-winprobe.exe`
   - Separate process from `localtrace.exe`.
   - Captures Windows activity signals.
   - Does not write SQLite directly.
   - Does not expose a public interface.
   - Sends JSON raw events to `localtrace.exe`.

3. LocalTrace Browser Extension
   - Chrome/Edge Manifest V3.
   - Sends browser activity events to `localtrace.exe`.
   - Uses `fetch` to localhost.
   - Does not use Native Messaging.

4. `localtrace-skill`
   - Agent-facing skill.
   - Calls the local HTTP API.
   - Does not import LocalTrace internals.
   - Does not read SQLite directly.
   - Computes summaries from raw events in scripts.

Web display:

- A local Web UI renders Today, Timeline, Top apps/domains, Now, settings,
  privacy rules, and health checks from raw events.
- Derived views are computed in the Web UI and are not stored as derived core
  tables.

## Capture Scope

LocalTrace preserves capture signals for Windows focus, non-browser audio, and
browser focus/audio.

Windows probe events:

- `app_active`
- `app_audio`
- `app_audio_stop`

Browser extension events:

- `tab_active`
- `tab_audio_stop`
- `activity = focus`
- `activity = audio`

Idle behavior:

- Idle remains internal gating in the Windows probe.
- Idle is not stored as `idle_start` or `idle_end` in v1.
- Event gaps plus skill-side analysis can infer idle periods.

Privacy defaults:

- Window titles are off by default.
- Tab titles are off by default.
- Full executable paths are off by default.
- Full URLs are not captured by default.
- Web page content is never captured.
- Screenshots are never captured.
- Keyboard input is never captured.

## Data Model

LocalTrace stores raw events only.

Required tables:

```text
events
privacy_rules
```

Configuration is stored in `config.json`, not SQLite.

No derived tables:

```text
blocks
timeline_segments
top_items
reports
report_todos
review_notes
```

## Event Time Semantics

Each event has two distinct times:

- `observed_at`: when the source observed the activity.
- `received_at`: when `localtrace.exe` received the event.

`observed_at` drives analysis. `received_at` supports diagnostics, ordering issues, and source health checks.

Events do not store `duration_ms` in v1. Duration is derived from neighboring events by skill scripts.

## Local API Rules

Default endpoint:

```text
http://127.0.0.1:8765
```

Rules:

- Bind host is fixed to `127.0.0.1`.
- Port is configurable.
- No token.
- No login.
- No auth.
- No LAN.
- No cloud.

## Local API Draft

```text
GET  /health

POST /events
GET  /events?from=&to=&source=&kind=&limit=

GET  /settings
POST /settings

GET    /privacy/rules
POST   /privacy/rules
DELETE /privacy/rules/{id}

POST /tracking/pause
POST /tracking/resume
GET  /tracking/status

POST /data/delete
```

Only `/events` is the stable data interface for source components and skills. Higher-level analysis belongs in `localtrace-skill` scripts unless a later spec explicitly promotes it to core.

## Configuration

Default data directory:

```text
%LOCALAPPDATA%\LocalTrace\
```

Files:

```text
%LOCALAPPDATA%\LocalTrace\config.json
%LOCALAPPDATA%\LocalTrace\localtrace.db
%LOCALAPPDATA%\LocalTrace\logs\
```

Draft `config.json`:

```json
{
  "api": {
    "port": 8765
  },
  "capture": {
    "poll_ms": 1000,
    "heartbeat_seconds": 60,
    "idle_cutoff_seconds": 300,
    "store_titles": false,
    "store_exe_path": false,
    "track_browser": true,
    "track_audio": true
  },
  "privacy": {}
}
```

The host is not configurable. Title storage is controlled only by
`capture.store_titles`.

## Component Independence

Runtime components communicate only through local HTTP JSON.

Forbidden:

- Browser extension writes SQLite.
- Web UI reads SQLite.
- Skill reads SQLite.
- Windows probe writes SQLite.
- Skill imports LocalTrace Python internals.
- Web UI imports LocalTrace internals.
- Probe imports storage internals.

Allowed:

- `localtrace-winprobe.exe` posts JSON events.
- Browser extension posts JSON events.
- Web UI calls local HTTP endpoints.
- Skill scripts call local HTTP endpoints.

## Web UI V1 Scope

V1 Web UI includes only:

- Settings.
- Privacy rules.
- Health checks.

Settings:

- Port.
- Poll interval.
- Heartbeat seconds.
- Title storage on/off.
- Exe path storage on/off.
- Browser tracking on/off.
- App audio tracking on/off.
- Pause/resume.

Privacy:

- App/domain drop rule.
- App/domain mask rule.

Health:

- `localtrace.exe` running.
- `localtrace-winprobe.exe` running.
- Browser extension last seen.
- DB path.
- Recent event count.

V1 Web UI does not include:

- Report generation UI.
- Block review workflow.
- Task planning UI.
- Charts.

## Skill V1 Scope

`localtrace-skill` includes script-style tools:

- `localtrace_health`
- `localtrace_recent_events`
- `localtrace_events_between`
- `localtrace_day_summary`
- `localtrace_explain_gap`

The skill computes summaries from raw events at call time. It does not require derived tables in LocalTrace core.

MCP is a second-stage option, not v1 required scope.

## Development Tools Boundary

These tools are development process tools, not LocalTrace runtime dependencies:

- Codebase Memory.
- Task Master AI.
- Playwright.
- Firecrawl.
- Context7.

LocalTrace must document how they are used, but runtime binaries must not depend on them.

## Phase Plan

P0. Spec + Infrastructure Freeze

- Write specs.
- Define event schema.
- Define workflow and review gates.
- Define infrastructure.
- Define issue workflow.
- No implementation code until human review passes.

P1. Core Skeleton

- Python HTTP server.
- `config.json`.
- SQLite schema.
- `GET /health`.
- `POST /events`.
- `GET /events`.

P2. Winprobe

- Independent process.
- Capture existing Windows signals.
- Preserve current idle gating semantics.
- POST to `/events`.

P3. Browser Extension

- Adapt current MV3 extension.
- Endpoint becomes `/events`.
- Align event schema.

P4. Web Settings

- Settings.
- Privacy.
- Health.
- No dashboard.

P5. Skill

- Health.
- Recent events.
- Events between.
- Day summary.
- Explain gap.

P6. Packaging / Autostart

- PyInstaller or equivalent.
- Zip artifact.
- Extension package.
- GitHub Release.
- HKCU Run autostart.
- Install/uninstall scripts.

## P0 Acceptance Checklist

- [ ] Human reviewed `LOCALTRACE_SPEC.md`.
- [ ] Human reviewed `ARCHITECTURE.md`.
- [ ] Human reviewed `EVENT_SCHEMA.md`.
- [ ] Human reviewed `WORKFLOW.md`.
- [ ] Human reviewed `INFRASTRUCTURE.md`.
- [ ] Human reviewed `ISSUES.md`.
- [ ] Human explicitly approved moving to P1.
