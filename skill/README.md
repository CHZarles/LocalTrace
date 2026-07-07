# LocalTrace Skill

The LocalTrace skill is a script-style agent interface over the local
LocalTrace HTTP JSON API.

## Install

This skill is documented for a Windows agent running beside the LocalTrace
runtime. `localtrace.exe` must be installed and `localtrace-winprobe.exe` must be
available for capture.

From the repository root, run one PowerShell command:

```powershell
powershell -ExecutionPolicy Bypass -File .\skill\install.ps1
```

Direct Python fallback on Windows:

```powershell
python .\skill\install.py
```

These commands install the skill into:

```text
%USERPROFILE%\.agents\skills\localtrace
```

They also create the direct command wrapper:

```text
%LOCALAPPDATA%\LocalTrace\bin\localtrace-skill.cmd
```

The skill has no third-party runtime dependencies. It only needs a Python
interpreter and a running LocalTrace core at `http://127.0.0.1:8765`.
During install, the installer also tries to start the installed Windows runtime
from `%LOCALAPPDATA%\LocalTrace\App` so app capture can begin immediately. If
the runtime package is missing, the installer reports that in its JSON output.

## Commands

```powershell
localtrace-skill.cmd dashboard
localtrace-skill.cmd focus-switches
localtrace-skill.cmd health
localtrace-skill.cmd recent-events --limit 5 --lookback-days 30
localtrace-skill.cmd events-between --from 2026-07-01T00:00:00.000Z --to 2026-07-02T00:00:00.000Z
localtrace-skill.cmd day-summary --date 2026-07-01
localtrace-skill.cmd explain-gap --from 2026-07-01T12:00:00.000Z --to 2026-07-01T13:00:00.000Z
```

Without installing first, use the dispatcher directly:

```powershell
python .\skill\scripts\localtrace.py health
```

`localtrace_recent_events.py` scans backward from `--to` in 24-hour windows and
stops once it has enough events. If a window exceeds `--scan-limit`, it returns a
partial-error JSON payload instead of silently truncating.

`focus-switches` reads the past 3 days of focus events (`app_active` and
`tab_active`) and returns factual JSON: switch count, switch list,
`target_durations`, title capture coverage, idle/unknown seconds, and
`prompt_context`. It does not rate attention by itself; agents should combine
`prompt_context` with the user's own prompt when the user asks for an AI
judgment.

Use `title_capture.windows_probe` when checking whether desktop app titles are
present in the captured data. If `with_title_count` is zero, report that the
current sample has no Windows app titles; do not conclude that `windows_probe`
cannot track titles.

Use `--base-url` or `LOCALTRACE_BASE_URL` to target a non-default LocalTrace
port on `127.0.0.1`. The default is `http://127.0.0.1:8765`; base URLs with
`localhost`, paths, query strings, or fragments are rejected.

Constraints:

- Scripts call LocalTrace through local HTTP JSON only.
- Scripts do not read `localtrace.db`.
- Scripts do not import `localtrace_core`.
- Scripts do not add auth, LAN, cloud, MCP, or derived storage behavior.
