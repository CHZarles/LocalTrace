---
name: localtrace
description: Use when you need to inspect LocalTrace health, query captured raw events, summarize a day, or explain observed activity gaps from the local LocalTrace HTTP API.
---

# LocalTrace Skill

Use this skill when the user asks about locally captured LocalTrace activity.
The scripts call the LocalTrace core over loopback HTTP JSON only. They do not
read SQLite, import LocalTrace runtime internals, use auth tokens, or contact
cloud services.

Default core URL:

```text
http://127.0.0.1:8765
```

Override the port with `--base-url` or `LOCALTRACE_BASE_URL` when testing or
when the user configured a different port. The host must remain `127.0.0.1`,
with no path, query string, or fragment.

## Tools

- `scripts/localtrace_health.py`: print `GET /health`.
- `scripts/localtrace_recent_events.py`: print recent raw events by scanning
  backward from `--to` in bounded 24-hour windows.
- `scripts/localtrace_events_between.py`: print raw events in an RFC3339 UTC
  range.
- `scripts/localtrace_day_summary.py`: compute a same-day summary from raw
  events.
- `scripts/localtrace_explain_gap.py`: inspect events before, inside, and after
  a requested observed-time window.

All scripts print machine-readable JSON to stdout. On expected failures, scripts
return non-zero and print `{"ok": false, "error": "..."}`.
