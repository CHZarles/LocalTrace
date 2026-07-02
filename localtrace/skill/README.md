# LocalTrace Skill

The LocalTrace skill is a script-style agent interface over the local
LocalTrace HTTP JSON API.

Manual examples:

```bash
python localtrace/skill/scripts/localtrace_health.py
python localtrace/skill/scripts/localtrace_recent_events.py --limit 5 --lookback-days 30
python localtrace/skill/scripts/localtrace_events_between.py --from 2026-07-01T00:00:00.000Z --to 2026-07-02T00:00:00.000Z
python localtrace/skill/scripts/localtrace_day_summary.py --date 2026-07-01
python localtrace/skill/scripts/localtrace_explain_gap.py --from 2026-07-01T12:00:00.000Z --to 2026-07-01T13:00:00.000Z
```

`localtrace_recent_events.py` scans backward from `--to` in 24-hour windows and
stops once it has enough events. If a window exceeds `--scan-limit`, it returns a
partial-error JSON payload instead of silently truncating.

Use `--base-url` or `LOCALTRACE_BASE_URL` to target a non-default LocalTrace
port. The default is `http://127.0.0.1:8765`.

Constraints:

- Scripts call LocalTrace through local HTTP JSON only.
- Scripts do not read `localtrace.db`.
- Scripts do not import `localtrace_core`.
- Scripts do not add auth, LAN, cloud, MCP, or derived storage behavior.
