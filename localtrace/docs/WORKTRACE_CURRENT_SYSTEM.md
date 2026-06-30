# WorkTrace Current System

Status: current-system analysis for human review.

This document describes the current WorkTrace capture path as observed from the
current worktree. It is analysis only. It does not approve LocalTrace
implementation work.

Important worktree note:

- `core/recorder_core/src/main.rs` is modified in the current worktree.
- `core/recorder_core/src/activity.rs` is untracked in the current worktree, but
  `main.rs` imports `mod activity`.
- This document treats the current worktree as the system being analyzed.

## Component Map

```text
Chrome/Edge extension
  extension/service_worker.js
  extension/manifest.json
        |
        | POST http://127.0.0.1:17600/event
        v
Rust core HTTP service
  core/recorder_core/src/main.rs
  core/recorder_core/src/activity.rs
        |
        | SQLite
        v
  data/recorder-core.db or %LOCALAPPDATA%\WorkTrace\recorder-core.db

Windows collector
  collectors/windows_collector/src/main.rs
        |
        | POST http://127.0.0.1:17600/event
        v
Rust core HTTP service

Flutter desktop UI
  ui_flutter/template/lib/api/core_client.dart
  worktrace_ui/lib/api/core_client.dart
        |
        | GET/POST local Core APIs
        v
Rust core HTTP service
```

Secondary or historical component:

```text
WinUI prototype
  windows/src/WorkTrace.Windows/*
        |
        | In-memory local ingest demo only
        v
  Not the main current data path
```

## Component Roles

### `core/recorder_core`

Role:

- Rust Axum local HTTP service.
- Default listen address is `127.0.0.1:17600`.
- Owns SQLite writes.
- Applies tracking pause, privacy rules, title stripping, and exe path stripping.
- Computes `now`, `blocks`, `timeline`, exports, reports, todos, and review
  state.

Key files:

- `core/recorder_core/src/main.rs`
- `core/recorder_core/src/activity.rs`
- `core/recorder_core/Cargo.toml`

Evidence:

- Default port and DB args: `core/recorder_core/src/main.rs:101`.
- `IngestEvent` fields: `core/recorder_core/src/main.rs:215`.
- HTTP routes: `core/recorder_core/src/main.rs:991`.
- SQLite schema: `core/recorder_core/src/main.rs:5111`.
- Event insert: `core/recorder_core/src/main.rs:5668`.
- Activity derivation: `core/recorder_core/src/activity.rs:26`.

Current core routes include:

```text
GET  /health
POST /event
GET  /events
GET  /now

GET  /tracking/status
POST /tracking/pause
POST /tracking/resume

GET  /settings
POST /settings

GET  /timeline/day
GET  /blocks/today
GET  /blocks/due
POST /blocks/review
POST /blocks/delete

GET    /privacy/rules
POST   /privacy/rules
DELETE /privacy/rules/:id

POST /data/delete_day
POST /data/wipe

GET /export/markdown
GET /export/csv

GET  /reports/settings
POST /reports/settings
POST /reports/generate/daily
POST /reports/generate/weekly
GET  /reports/todos
POST /reports/todos
DELETE /reports/todos/:id
GET  /reports
POST /reports
GET  /reports/:id
DELETE /reports/:id
```

LocalTrace implication:

- The current core is too broad to carry over as-is.
- LocalTrace core should keep the raw event ingest/storage/privacy subset.
- LocalTrace should not keep reports, todos, review reminders, block review, or
  generated exports in core.

### `collectors/windows_collector`

Role:

- Rust Windows-only collector.
- Polls Win32 foreground window state.
- Polls Windows CoreAudio sessions for non-browser background audio.
- Posts JSON events to Core.
- Avoids duplicate collectors with a Windows mutex.
- Also contains review reminder notification behavior, which is out of scope for
  LocalTrace v1.

Key files:

- `collectors/windows_collector/src/main.rs`
- `collectors/windows_collector/README.md`
- `collectors/windows_collector/Cargo.toml`

Evidence:

- CLI args and privacy defaults: `collectors/windows_collector/src/main.rs:3`.
- POST endpoint construction: `collectors/windows_collector/src/main.rs:146`.
- Foreground `app_active` event: `collectors/windows_collector/src/main.rs:180`.
- Background `app_audio` and `app_audio_stop` events:
  `collectors/windows_collector/src/main.rs:218`.
- Idle detection: `collectors/windows_collector/src/main.rs:608`.
- Foreground app detection: `collectors/windows_collector/src/main.rs:628`.
- CoreAudio session detection: `collectors/windows_collector/src/main.rs:691`.
- Browser executable exclusion for app audio:
  `collectors/windows_collector/src/main.rs:800`.

LocalTrace implication:

- The foreground app and CoreAudio parts are directly relevant.
- Review notification code should not move into LocalTrace v1.
- The collector should become `localtrace-winprobe.exe` or equivalent.

### `extension`

Role:

- Chrome/Edge Manifest V3 extension.
- Uses `chrome.tabs`, `chrome.storage`, `chrome.alarms`, and `chrome.offscreen`.
- Posts browser events to Core with `fetch`.
- Tracks hostname only by default.
- Optional tab title sending is off by default.
- Uses explicit stop markers for background tab audio.

Key files:

- `extension/manifest.json`
- `extension/service_worker.js`
- `extension/popup.js`
- `extension/README.md`

Evidence:

- MV3 permissions and localhost host permissions:
  `extension/manifest.json:1`.
- Defaults: `extension/service_worker.js:1`.
- Hostname-only URL parsing: `extension/service_worker.js:109`.
- POST `/event`: `extension/service_worker.js:220`.
- `tab_audio_stop`: `extension/service_worker.js:270`.
- `tab_active` focus/audio selection: `extension/service_worker.js:312`.
- Extension README behavior summary: `extension/README.md:3`.

LocalTrace implication:

- Keep MV3 plus localhost `fetch`.
- Keep hostname-only default.
- Keep optional title toggle.
- Do not introduce Native Messaging.

### `worktrace_ui` And `ui_flutter/template`

Role:

- Flutter desktop UI.
- `ui_flutter/template` is the template source.
- `worktrace_ui` is the generated/runnable Flutter project.
- UI does not read SQLite directly.
- UI talks to Core over HTTP through `CoreClient`.
- UI can start/stop Core and Collector in packaged or repo mode.

Key files:

- `ui_flutter/template/lib/api/core_client.dart`
- `ui_flutter/template/lib/screens/today_screen.dart`
- `ui_flutter/template/lib/screens/settings_screen.dart`
- `ui_flutter/template/lib/utils/desktop_agent_io.dart`
- `worktrace_ui/lib/api/core_client.dart`

Evidence:

- Current product summary: `README.md:22`.
- UI API client routes: `ui_flutter/template/lib/api/core_client.dart:12`.
- Today screen polls Now, blocks, timeline:
  `ui_flutter/template/lib/screens/today_screen.dart:128`.
- Settings screen manages health, privacy, tracking, data, startup, updates:
  `ui_flutter/template/lib/screens/settings_screen.dart:42`.
- Desktop agent starts `recorder_core.exe` and `windows_collector.exe`:
  `ui_flutter/template/lib/utils/desktop_agent_io.dart:310`.
- Packaged data directory:
  `ui_flutter/template/lib/utils/desktop_agent_io.dart:133`.

LocalTrace implication:

- UI information architecture can be reused later for a local Web UI.
- The visible Flutter client is not part of LocalTrace v1.
- The agent-start logic is useful conceptually, but LocalTrace should own its own
  simpler background startup/install path.

### `windows/src/WorkTrace.Windows`

Role:

- WinUI/C# prototype or earlier local ingest app.
- Starts an ASP.NET local server on `127.0.0.1:17600`.
- Accepts `/event` and keeps recent events in memory.
- Requires browser `domain`.
- Does not represent the main current SQLite-backed path.

Key files:

- `windows/src/WorkTrace.Windows/App.xaml.cs`
- `windows/src/WorkTrace.Windows/Services/LocalIngestServer.cs`
- `windows/src/WorkTrace.Windows/Services/IngestEventStore.cs`
- `windows/src/WorkTrace.Windows/Models/IngestEvent.cs`

Evidence:

- Startup: `windows/src/WorkTrace.Windows/App.xaml.cs:18`.
- Local server: `windows/src/WorkTrace.Windows/Services/LocalIngestServer.cs:25`.
- In-memory store: `windows/src/WorkTrace.Windows/Services/IngestEventStore.cs:5`.

LocalTrace implication:

- Do not migrate this path.
- It is useful only as historical evidence of an earlier ingest prototype.

### `schemas/ingest-event.schema.json`

Role:

- Documents current ingest event shapes.
- Allows extra properties.
- Declares current sources and event names.

Current source enum:

```text
browser_extension
windows_collector
```

Current event enum:

```text
tab_active
tab_audio_stop
app_active
app_audio
app_audio_stop
```

Evidence:

- Source and event enums: `schemas/ingest-event.schema.json:15`.
- Browser event shapes: `schemas/ingest-event.schema.json:24`.
- Windows event shapes: `schemas/ingest-event.schema.json:72`.

LocalTrace implication:

- This schema is the clearest source for "what the old system captures now".
- LocalTrace should preserve these event meanings, while renaming sources if
  needed.

## Capture Signal Inventory

### Windows Signals

#### `app_active`

Produced by:

- `collectors/windows_collector/src/main.rs`

Trigger:

- Foreground app changes, or heartbeat is due.
- Heartbeat default is 60 seconds.
- Poll interval default is 1000 ms.
- Not emitted while system idle duration is above the idle cutoff.

Payload:

```json
{
  "v": 1,
  "ts": "RFC3339 timestamp",
  "source": "windows_collector",
  "event": "app_active",
  "app": "Code.exe",
  "title": "optional window title",
  "exePath": "optional full path",
  "pid": 1234
}
```

Privacy:

- Collector sends `title` only with `--send-title`.
- Collector sends `exePath` only with `--send-exe-path`.
- Core still strips `title` unless `store_titles` is true.
- Core strips `exePath` and `pid` unless `store_exe_path` is true.

LocalTrace decision:

- Preserve `app_active`.
- Keep title off by default.
- Keep full path off by default.
- Consider whether `pid` should be stored separately; current Core strips it with
  `store_exe_path=false`.

#### `app_audio`

Produced by:

- `collectors/windows_collector/src/main.rs`

Trigger:

- Windows CoreAudio reports an active non-browser audio session.
- Heartbeat default is 60 seconds.
- Browser executables are excluded so browser audio is handled by the extension.

Payload:

```json
{
  "v": 1,
  "ts": "RFC3339 timestamp",
  "source": "windows_collector",
  "event": "app_audio",
  "activity": "audio",
  "app": "QQMusic.exe",
  "exePath": "optional full path",
  "pid": 1234
}
```

Privacy:

- `exePath` is optional at collector level.
- Core strips `exePath` and `pid` unless `store_exe_path` is true.

LocalTrace decision:

- Preserve `app_audio`.
- Keep browser-exe exclusion.
- Keep it independent from foreground focus.

#### `app_audio_stop`

Produced by:

- `collectors/windows_collector/src/main.rs`

Trigger:

- Previously active non-browser audio session disappears after a successful poll.
- Transient audio polling errors do not emit a stop marker.

Payload:

```json
{
  "v": 1,
  "ts": "RFC3339 timestamp",
  "source": "windows_collector",
  "event": "app_audio_stop",
  "activity": "audio",
  "app": "QQMusic.exe",
  "reason": "no_active_audio_sessions"
}
```

LocalTrace decision:

- Preserve explicit stop marker.
- It prevents stale background-audio attribution.

### Browser Signals

#### `tab_active` With `activity=focus`

Produced by:

- `extension/service_worker.js`

Trigger:

- Browser window is focused.
- Active tab changes, URL/title/audible state changes, extension heartbeat is
  due, or force send is requested.

Payload:

```json
{
  "v": 1,
  "ts": "ISO timestamp",
  "source": "browser_extension",
  "event": "tab_active",
  "activity": "focus",
  "browser": "chrome",
  "domain": "example.com",
  "title": "optional tab title",
  "windowId": 1,
  "tabId": 123
}
```

Privacy:

- Extension sends hostname only, not full URL.
- Extension sends `title` only if popup setting `sendTitle` is true.
- Core still strips `title` unless `store_titles` is true.

LocalTrace decision:

- Preserve.
- Continue to reject full URL capture by default.

#### `tab_active` With `activity=audio`

Produced by:

- `extension/service_worker.js`

Trigger:

- Browser is not focused.
- At least one audible tab exists.
- Extension chooses the previous audible tab if still audible, otherwise the
  most recently accessed audible tab.

Payload:

```json
{
  "v": 1,
  "ts": "ISO timestamp",
  "source": "browser_extension",
  "event": "tab_active",
  "activity": "audio",
  "browser": "chrome",
  "domain": "youtube.com",
  "windowId": 1,
  "tabId": 123
}
```

LocalTrace decision:

- Preserve.
- This is how browser background audio is represented.

#### `tab_audio_stop`

Produced by:

- `extension/service_worker.js`

Trigger:

- Browser returns to foreground after tracking an audible background tab.
- No audible tabs remain.
- Tracked audible tab is closed or no longer detectable.

Payload:

```json
{
  "v": 1,
  "ts": "ISO timestamp",
  "source": "browser_extension",
  "event": "tab_audio_stop",
  "activity": "audio",
  "browser": "chrome",
  "domain": "youtube.com",
  "reason": "browser_focused"
}
```

LocalTrace decision:

- Preserve explicit stop marker.
- It is required for accurate background browser audio end times.

## Idle Handling

Current behavior:

- Windows collector calls `GetLastInputInfo` and `GetTickCount64`.
- If idle seconds exceed `--idle-cutoff-seconds`, collector stops emitting
  `app_active` and resets its last foreground key.
- It does not emit `idle_start` or `idle_end`.
- Current README says this idle cutoff only affects `app_active`; background
  audio still follows CoreAudio state.
- Core and `activity.rs` also cap derived durations by `idle_cutoff_seconds`.
- Audio duration gets a shorter cap through `AUDIO_IDLE_CUTOFF_SECONDS`.

LocalTrace decision:

- Preserve idle as probe-internal gating.
- Do not store idle events in v1.
- Skill scripts can infer idle gaps from event spacing.

## Privacy Behavior

Current privacy has two layers.

Collector or extension send layer:

- Windows title is off by default.
- Windows full exe path is off by default.
- Browser title is off by default.
- Browser full URL is never sent; extension stores only hostname.

Core persistence layer:

- `store_titles=false` by default strips all titles before storage.
- `store_exe_path=false` by default strips `exePath` and `pid` from
  `payload_json`.
- `privacy_rules` can `drop` or `mask` exact app/domain values.
- `mask` changes entity to `__hidden__` and removes high-sensitive fields from
  payload.

LocalTrace decision:

- Keep Core-owned privacy filtering.
- Keep titles and full paths off by default.
- Keep privacy rules.
- Avoid storing credentials or report API keys in LocalTrace.

## Data Flow

### 1. Startup

Current packaged flow:

- Flutter UI locates bundled `recorder_core.exe` and `windows_collector.exe`.
- UI starts Core with `--listen host:port --db dbPath`.
- UI starts Collector with `--core-url`, title/audio/review flags, and idle
  settings.
- UI writes `agent-pids.json` under the data directory.

Evidence:

- `ui_flutter/template/lib/utils/desktop_agent_io.dart:310`.

LocalTrace decision:

- Replace visible desktop-client ownership with a background user-session app.
- Keep the idea that one owner starts/checks the Windows probe.

### 2. Event Production

Windows collector:

- Polls foreground app and CoreAudio.
- Produces `app_active`, `app_audio`, `app_audio_stop`.
- Sends each event to `/event`.

Browser extension:

- Uses Chrome APIs to detect focused tab or background audible tab.
- Produces `tab_active` and `tab_audio_stop`.
- Sends each event to `/event`.

### 3. Core Ingest

Core `POST /event` does this:

1. Accepts JSON as `serde_json::Value`.
2. Deserializes into `IngestEvent`.
3. Validates version and RFC3339 timestamp.
4. Requires `domain` for browser events.
5. Requires `app` for Windows events.
6. Drops event if tracking is paused.
7. Applies exact-match privacy rules.
8. Applies global title/path stripping.
9. Serializes filtered payload to JSON.
10. Inserts a row into `events`.

Evidence:

- `post_event`: `core/recorder_core/src/main.rs:1161`.
- Validation: `core/recorder_core/src/main.rs:1187`.
- Entity selection: `core/recorder_core/src/main.rs:1199`.
- Pause check: `core/recorder_core/src/main.rs:1251`.
- Privacy rules: `core/recorder_core/src/main.rs:1265`.
- Global privacy: `core/recorder_core/src/main.rs:1307`.
- Insert: `core/recorder_core/src/main.rs:1336`.

### 4. SQLite Storage

Current tables:

```text
events
block_reviews
app_settings
privacy_rules
tracking_state
report_settings
reports
report_todos
```

Current `events` columns:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
ts TEXT NOT NULL
source TEXT NOT NULL
event TEXT NOT NULL
entity TEXT
title TEXT
payload_json TEXT NOT NULL
```

Current behavior:

- Raw events are stored in `events`.
- `blocks` and `timeline_segments` are not stored as tables.
- `blocks` and `timeline_segments` are derived from event rows at request time.
- `block_reviews`, `reports`, and `report_todos` are stored tables.
- Settings are stored in SQLite, not a separate config file.

LocalTrace decision:

- Keep `events` and `privacy_rules` conceptually.
- Move settings to `config.json`.
- Drop `block_reviews`, `report_settings`, `reports`, and `report_todos`.
- Add `observed_at` and `received_at` split in LocalTrace schema.

### 5. Derived Activity

Core derives activity on demand:

- `/now` scans recent events and reports current focus/tab/audio state.
- `/blocks/today` loads day events and calls `build_blocks`.
- `/timeline/day` loads day events and calls `build_timeline_segments`.
- Report generation loads day or week events, calls `build_day_activity`, and
  builds an LLM input JSON.

Important current rules:

- Focus events and audio events are split.
- Browser foreground app plus fresh tab event resolves to domain instead of
  browser executable.
- Domain freshness window is 300 seconds.
- Durations come from gaps between neighboring event timestamps.
- Gaps are capped by idle cutoff.
- Background audio is attached separately to blocks.
- Stop markers end background audio attribution.

Evidence:

- `build_day_activity`: `core/recorder_core/src/activity.rs:26`.
- Event split: `core/recorder_core/src/activity.rs:108`.
- Browser app/domain resolution: `core/recorder_core/src/activity.rs:193`.
- Idle gap split: `core/recorder_core/src/activity.rs:258`.
- Timeline derivation: `core/recorder_core/src/activity.rs:328`.
- Background audio attachment: `core/recorder_core/src/activity.rs:506`.

LocalTrace decision:

- Do not store derived blocks/top/timeline tables.
- Move day timeline/top computations into `localtrace-skill` scripts first.
- Reuse the algorithm ideas, not the current core coupling.

### 6. UI Read Path

Flutter UI reads only from Core HTTP APIs:

- `GET /health`
- `GET /now`
- `GET /events`
- `GET /blocks/today`
- `GET /blocks/due`
- `GET /timeline/day`
- `GET /settings`
- `POST /settings`
- `GET/POST/DELETE /privacy/rules`
- `POST /tracking/pause`
- `POST /tracking/resume`
- report and todo APIs

Evidence:

- `ui_flutter/template/lib/api/core_client.dart:12`.

LocalTrace decision:

- Optional Web UI can reuse the current information architecture later.
- LocalTrace v1 Web UI should be settings/privacy/health only.
- Analysis views should first live in the skill.

## Keep, Delete, Defer, Transform

| Area | Decision | Reason |
| --- | --- | --- |
| `app_active` capture | Keep | Core Windows activity signal. |
| `app_audio` capture | Keep | Captures non-browser background audio. |
| `app_audio_stop` marker | Keep | Ends app audio attribution accurately. |
| `tab_active activity=focus` | Keep | Core browser usage signal. |
| `tab_active activity=audio` | Keep | Captures browser background audio. |
| `tab_audio_stop` marker | Keep | Ends browser audio attribution accurately. |
| Hostname-only browser capture | Keep | Good privacy boundary. |
| Optional titles | Keep configurable | Useful but must stay off by default. |
| Optional full exe path | Keep configurable | Useful diagnostics, high sensitivity. |
| Core-owned privacy filtering | Keep | Prevents sources from deciding persistence. |
| Raw `events` storage | Keep | Main LocalTrace data asset. |
| `privacy_rules` | Keep | Local user control. |
| `tracking_state` pause/resume | Keep or simplify | Useful operational control. |
| Flutter desktop client | Delete from v1 | User does not want foreground app/window. |
| WinUI prototype | Delete | Not main path and in-memory only. |
| Planner | Delete | Edge feature, not capture. |
| Report TODOs | Delete | Edge feature, not capture. |
| LLM reports | Delete | Adds cloud/API-key concerns. |
| Report scheduler | Delete | Edge feature and not local capture. |
| Block reviews | Delete from v1 | Review workflow is not core capture. |
| Review reminders/toasts | Delete from v1 | Notification workflow, not capture. |
| Markdown/CSV exports | Defer | Can be skill-side or later tool. |
| Web display | Defer | Optional, reuse IA later. |
| MCP | Defer | Skill scripts first. |
| Now/timeline/top summaries | Transform | Compute from raw events in skill scripts. |
| Core settings in SQLite | Transform | Move to `config.json`. |
| `POST /event` endpoint | Revisit | LocalTrace draft uses `POST /events`; compatibility decision needed. |
| Old port `17600` | Transform | LocalTrace draft uses configurable port default `8765`. |

## Migration Risks

### 1. Current core is a mixed-purpose module

`core/recorder_core/src/main.rs` currently contains:

- HTTP routing.
- SQLite schema and migrations.
- Ingest validation.
- Privacy filtering.
- Settings.
- Tracking pause/resume.
- Block review.
- Data deletion.
- Markdown/CSV exports.
- Report settings.
- LLM report generation.
- Report scheduler.
- Report TODOs.

Risk:

- Copying this module would preserve the old complexity.

Mitigation:

- Port only the raw ingest, storage, settings, privacy, and health concepts.
- Do not port reports, TODOs, review, reminders, exports, or scheduler.

### 2. Current activity algorithm is valuable but coupled

`activity.rs` contains useful logic:

- Focus/audio separation.
- Browser executable to domain resolution.
- Idle cutoff duration capping.
- Audio stop handling.
- Timeline segment generation.
- Background audio attachment.

Risk:

- Moving it into LocalTrace core would recreate derived behavior in the core.

Mitigation:

- Reuse the ideas in `localtrace-skill` first.
- Keep LocalTrace core raw-event oriented.

### 3. Time semantics need correction

Current WorkTrace stores one timestamp:

```text
events.ts
```

This timestamp is source-observed time. There is no separate receive/write time.

Risk:

- Late delivery, extension sleep, collector restart, and queue delay are hard to
  diagnose.

Mitigation:

- LocalTrace should store both `observed_at` and `received_at`.

### 4. Privacy is split across source and core

Current behavior is good in principle:

- Sources avoid sending sensitive data by default.
- Core still strips sensitive fields before persistence.

Risk:

- If LocalTrace only relies on source settings, a bug in the extension/probe can
  leak title/path data into SQLite.

Mitigation:

- Keep core-owned persistence filtering.
- Treat source flags as first-line minimization only.

### 5. Browser extension uses broad localhost host permissions

Current extension allows:

```text
http://127.0.0.1:*/*
http://localhost:*/*
```

Risk:

- Convenient during development, but broader than LocalTrace's fixed loopback
  rule.

Mitigation:

- LocalTrace should keep host fixed to `127.0.0.1`.
- Decide whether extension host permissions can be narrowed to the configured
  loopback pattern while still supporting configurable ports.

### 6. Old reports bring API-key and cloud concepts

Current report settings include:

- `api_base_url`
- `api_key`
- `model`
- daily/weekly prompts
- scheduler

Risk:

- This conflicts with the LocalTrace rule to stay local and avoid auth/token
  features.

Mitigation:

- Do not port report settings, report scheduler, or report generation.

### 7. Old UI starts and supervises background binaries

Current visible Flutter UI can start/stop Core and Collector.

Risk:

- LocalTrace should not depend on a visible client window for process ownership.

Mitigation:

- Move ownership to a background user-session app.
- Web settings page can call local APIs, but should not be the runtime owner.

### 8. Endpoint naming mismatch

Current WorkTrace ingest endpoint:

```text
POST /event
```

LocalTrace draft endpoint:

```text
POST /events
```

Risk:

- Reusing the existing extension/collector without changes would fail.

Mitigation:

- Decide during LocalTrace P1/P3 whether to support `/event` as compatibility or
  migrate sources to `/events`.

## What Can Be Copied

Good candidates:

- Windows foreground polling approach.
- Windows CoreAudio session approach.
- Browser executable exclusion for app audio.
- MV3 hostname-only browser capture.
- Explicit audio stop markers.
- Privacy double gate idea.
- SQLite WAL and simple raw event insert pattern.
- Duration derivation tests and examples from current activity tests.

Copy with caution:

- `activity.rs` algorithms, but into skill scripts first.
- Desktop agent startup ideas, but not the visible UI ownership model.
- Settings UI concepts, but as local Web settings later.

Do not copy:

- Report settings and API-key storage.
- LLM report generation.
- Report scheduler.
- Report TODOs.
- Block review workflow.
- Review notification/toast workflow.
- Visible Flutter client as the main product shape.
- WinUI prototype ingest path.

## LocalTrace Capture Baseline From Current WorkTrace

The minimal capture baseline to preserve is:

```text
Windows:
- app_active
- app_audio
- app_audio_stop

Browser:
- tab_active with activity=focus
- tab_active with activity=audio
- tab_audio_stop

Privacy defaults:
- no full URL
- no page body
- no screenshots
- no keyboard input
- no titles unless enabled
- no full exe path unless enabled
```

This baseline matches `localtrace/docs/LOCALTRACE_SPEC.md`.

## Review Checklist

- [ ] Component roles are accurate.
- [ ] Windows capture signals are complete.
- [ ] Browser capture signals are complete.
- [ ] Idle behavior is clear.
- [ ] Audio stop marker behavior is clear.
- [ ] SQLite storage boundary is clear.
- [ ] UI read path is clear.
- [ ] Derived block/timeline/report/todo behavior is separated from raw capture.
- [ ] Keep/delete/defer/transform matrix matches the intended LocalTrace scope.
- [ ] Migration risks are explicit enough to guide implementation issues.
