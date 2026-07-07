---
name: localtrace
description: Query a Windows LocalTrace runtime over loopback HTTP and summarize captured activity for agents. Use when the user asks what happened locally, what they did today, recent apps/tabs/audio, LocalTrace health, missing events, or activity gaps.
---

# LocalTrace Skill

LocalTrace records one Windows user's app focus, non-browser audio, and browser
tab activity as local raw events. Use this skill to query those events through
the local HTTP API; do not inspect storage or runtime internals.

## Quick start

Assume the agent is running on Windows and should talk to the core at:

```text
http://127.0.0.1:8765
```

If the wrapper is installed, start with health:

```powershell
%LOCALAPPDATA%\LocalTrace\bin\localtrace-skill.cmd health
```

If the skill is not installed yet, install it from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\skill\install.ps1
```

After installation, immediately relay `must_tell_user_zh` from the installer
JSON. Also include `browser_extension.unpacked_dir`,
`browser_extension.chrome_url`, and `browser_extension.edge_url` if present.
If `must_tell_user_zh` is absent, use `browser_extension.agent_message_zh`.
Tell the user only browser "Load unpacked" is manual. The installer attempts to
download, install, autostart, and start missing runtime files (`localtrace.exe`,
`localtrace-winprobe.exe`) by itself. If `runtime.ready_for_app_capture` is
false, report `runtime.reason` plus `runtime.install.reason`; do not ask for
manual runtime install unless automatic install failed and no retry remains.

Do not ask the user to run commands manually when this skill applies. Run the
smallest answering subcommand and summarize the JSON result.

## Workflows

1. Dashboard or "open LocalTrace": run `dashboard`; it opens the Web UI.
2. Health or "is tracking working": run `health`; report `ok`, tracking pause
   state, database presence, and recent source timestamps.
3. Focus switching or attention review: run `focus-switches`; report facts,
   `target_durations`, switches, idle/unknown time, `title_capture`, and
   `prompt_context`. Do not invent a rating unless the user provides an
   evaluation prompt.
4. Recent activity or "what was I doing": run `recent-events --limit 25`;
   group by time, app/domain, source, and kind.
5. One-day summary or "today": run `day-summary --date YYYY-MM-DD`; summarize
   event count, top entities, sources, and observed span.
6. Exact window or audit question: run `events-between --from ... --to ...`;
   keep RFC3339 UTC timestamps and include filters only when requested.
7. Missing activity or "gap": run `explain-gap --from ... --to ...`; report
   inside events, nearest before/after events, and whether context is exact.
8. Desktop app title or "does windows_probe capture titles": use
   `focus-switches` `title_capture.windows_probe` and, when needed, query raw
   `events-between --source windows_probe --kind app_active`. Do not say
   windows_probe cannot track titles just because current samples have null
   `title`; say the current captured data has no Windows app titles, then
   mention runtime version/restart state and `capture.store_titles`.

## Command reference

```powershell
localtrace-skill.cmd dashboard
localtrace-skill.cmd focus-switches
localtrace-skill.cmd health
localtrace-skill.cmd recent-events --limit 5 --lookback-days 30
localtrace-skill.cmd events-between --from 2026-07-01T00:00:00.000Z --to 2026-07-02T00:00:00.000Z
localtrace-skill.cmd day-summary --date 2026-07-01
localtrace-skill.cmd explain-gap --from 2026-07-01T12:00:00.000Z --to 2026-07-01T13:00:00.000Z
```

Use `--base-url` or `LOCALTRACE_BASE_URL` only for a non-default port. The host
must stay `127.0.0.1`; paths, query strings, fragments, `localhost`, HTTPS, LAN,
and cloud endpoints are invalid.

## Guardrails

- Do not read SQLite, including `localtrace.db`.
- Do not import LocalTrace runtime modules such as `localtrace_core`.
- Do not add auth, tokens, login, LAN access, cloud access, MCP, or derived
  storage.
- Do not ask for screenshots, keyboard logs, page bodies, full URLs, or manual
  exports.
- Treat `observed_at` as analysis time; `received_at` is diagnostic context.
- All tools print JSON. On non-zero exits, report the JSON `error` field and
  the command you tried.

## Bundled files

- `install.ps1` / `install.py`: installer and runtime/extension preparer.
- `scripts/localtrace.py` and `localtrace_*.py`: HTTP JSON query tools.
