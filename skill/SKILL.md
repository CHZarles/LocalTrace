---
name: localtrace
description: Query a Windows LocalTrace runtime over loopback HTTP and summarize captured activity for agents. Use when the user asks what happened locally, what they did today, recent apps/tabs/audio, LocalTrace health, missing events, or activity gaps.
---

# LocalTrace Skill

LocalTrace records one Windows user's app focus, non-browser audio, and browser
tab activity as local raw events. Use this skill to query those events through
the local HTTP API; do not inspect storage or runtime internals.

## Quick start

Assume the agent is running on Windows with `localtrace.exe` installed,
`localtrace-winprobe.exe` available for capture, and the core listening at:

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

After installation, immediately relay `browser_extension.unpacked_dir`,
`browser_extension.chrome_url`, and `browser_extension.edge_url` from the
installer JSON. Tell the user that only the browser "Load unpacked" step is
manual. If `browser_extension.agent_message_zh` is present, use it for the
Chinese user-facing message.

Do not ask the user to run commands manually when this skill applies. Run the
smallest subcommand that answers the user's question and summarize the JSON
result.

## Workflows

1. Dashboard or "open LocalTrace": run `dashboard`; it opens the Web UI.
2. Health or "is tracking working": run `health`; report `ok`, tracking pause
   state, database presence, and recent source timestamps.
3. Focus switching or attention review: run `focus-switches`; report facts,
   `target_durations`, switches, idle/unknown time, and `prompt_context`.
   Do not invent a rating unless the user provides an evaluation prompt.
4. Recent activity or "what was I doing": run `recent-events --limit 25`;
   group by time, app/domain, source, and kind.
5. One-day summary or "today": run `day-summary --date YYYY-MM-DD`; summarize
   event count, top entities, sources, and observed span.
6. Exact window or audit question: run `events-between --from ... --to ...`;
   keep RFC3339 UTC timestamps and include filters only when requested.
7. Missing activity or "gap": run `explain-gap --from ... --to ...`; report
   inside events, nearest before/after events, and whether context is exact.

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

- `install.ps1`: Windows one-command installer.
- `install.py`: copies the skill, installs `requirements.txt`, creates wrapper.
- `scripts/localtrace.py`: dispatcher used by `localtrace-skill.cmd`.
- `scripts/localtrace_*.py`: deterministic HTTP JSON query tools.
