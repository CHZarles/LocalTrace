# Event Schema

Status: draft for human review.

LocalTrace stores raw events only. The event schema is the central contract between sources, storage, Web UI, and agent skills.

## Stored Event Fields

```text
id              integer primary key
observed_at     text, RFC3339 UTC
received_at     text, RFC3339 UTC
source          text
seq             integer nullable
kind            text
entity_type     text
entity          text
title           text nullable
payload_json    text
```

Meaning:

- `observed_at`: time the source observed the event.
- `received_at`: time core received the event.
- `source`: event source.
- `seq`: optional per-source monotonically increasing number.
- `kind`: event kind.
- `entity_type`: app/domain/system.
- `entity`: entity value after privacy filtering.
- `title`: nullable; default null.
- `payload_json`: extra fields after privacy filtering.

## Sources

Allowed v1 sources:

```text
windows_probe
browser_extension
```

Reserved future source:

```text
manual
```

## Event Kinds

Preserved LocalTrace capture signals:

```text
app_active
app_audio
app_audio_stop
tab_active
tab_audio_stop
```

No v1 idle events:

```text
idle_start
idle_end
```

Idle remains probe-internal gating.

## Entity Types

```text
app
domain
system
```

Expected mapping:

```text
app_active       -> entity_type = app
app_audio        -> entity_type = app
app_audio_stop   -> entity_type = app
tab_active       -> entity_type = domain
tab_audio_stop   -> entity_type = domain
```

## Ingest Payload Draft

POST `/events` accepts a raw event JSON object:

```json
{
  "observed_at": "2026-07-01T10:30:00.000Z",
  "source": "windows_probe",
  "seq": 123,
  "kind": "app_active",
  "entity_type": "app",
  "entity": "Code.exe",
  "title": null,
  "payload": {
    "pid": 1234,
    "activity": "focus"
  }
}
```

Core sets:

```text
received_at
id
```

Core may alter:

```text
entity
title
payload
```

only to apply privacy settings and rules.

## Windows Probe Events

### `app_active`

```json
{
  "observed_at": "2026-07-01T10:30:00.000Z",
  "source": "windows_probe",
  "seq": 1,
  "kind": "app_active",
  "entity_type": "app",
  "entity": "Code.exe",
  "title": null,
  "payload": {
    "pid": 1234
  }
}
```

Optional payload fields:

```text
exe_path
```

`exe_path` is only present when explicitly enabled.

### `app_audio`

```json
{
  "observed_at": "2026-07-01T10:31:00.000Z",
  "source": "windows_probe",
  "seq": 2,
  "kind": "app_audio",
  "entity_type": "app",
  "entity": "Spotify.exe",
  "title": null,
  "payload": {
    "pid": 5678,
    "activity": "audio"
  }
}
```

### `app_audio_stop`

```json
{
  "observed_at": "2026-07-01T10:32:00.000Z",
  "source": "windows_probe",
  "seq": 3,
  "kind": "app_audio_stop",
  "entity_type": "app",
  "entity": "Spotify.exe",
  "title": null,
  "payload": {
    "pid": 5678,
    "activity": "audio",
    "reason": "no_active_audio_sessions"
  }
}
```

## Browser Extension Events

### `tab_active`

Focus activity:

```json
{
  "observed_at": "2026-07-01T10:33:00.000Z",
  "source": "browser_extension",
  "seq": 20,
  "kind": "tab_active",
  "entity_type": "domain",
  "entity": "github.com",
  "title": null,
  "payload": {
    "activity": "focus",
    "browser": "edge",
    "window_id": 1,
    "tab_id": 100
  }
}
```

Background audio activity:

```json
{
  "observed_at": "2026-07-01T10:34:00.000Z",
  "source": "browser_extension",
  "seq": 21,
  "kind": "tab_active",
  "entity_type": "domain",
  "entity": "youtube.com",
  "title": null,
  "payload": {
    "activity": "audio",
    "browser": "edge",
    "window_id": 2,
    "tab_id": 101
  }
}
```

### `tab_audio_stop`

```json
{
  "observed_at": "2026-07-01T10:35:00.000Z",
  "source": "browser_extension",
  "seq": 22,
  "kind": "tab_audio_stop",
  "entity_type": "domain",
  "entity": "youtube.com",
  "title": null,
  "payload": {
    "activity": "audio",
    "browser": "edge",
    "reason": "audible_tab_stopped",
    "window_id": 2,
    "tab_id": 101
  }
}
```

## Privacy Rules

Privacy actions:

```text
drop
mask
```

`drop`:

- Core accepts the request.
- Core does not store the event.

`mask`:

- Core stores the event.
- `entity` becomes `__hidden__`.
- `title` becomes null.
- sensitive payload fields are removed.

Privacy rule fields:

```text
id
entity_type
pattern
action
created_at
```

Domain rules should match subdomains. App rules may start as exact match.

## Settings Impact

If `store_titles = false`:

- `title` is stored as null.
- payload title fields are removed.

If `store_exe_path = false`:

- `exe_path` is removed from payload.

## Query Semantics

GET `/events` returns stored events after privacy filtering has already been applied.

Draft query parameters:

```text
from        RFC3339 inclusive
to          RFC3339 exclusive
source      optional
kind        optional
limit       optional, default 200
```

Default sort:

```text
observed_at ascending
id ascending
```

Recent events may support descending order later, but v1 spec starts with predictable ascending ranges.

## Event Schema Acceptance Checklist

- [ ] `observed_at` and `received_at` are distinct.
- [ ] Existing LocalTrace capture signals are preserved.
- [ ] Idle is not stored as raw events.
- [ ] No derived duration field is required.
- [ ] Titles and exe paths are disabled by default.
- [ ] Events are sufficient for skill-side timeline/top/day summary computation.
