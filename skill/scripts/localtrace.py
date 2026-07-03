from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    module: str
    description: str


COMMANDS = {
    "dashboard": Command("localtrace_dashboard", "Open the LocalTrace Web UI."),
    "focus-switches": Command(
        "localtrace_focus_switches", "Report focus-switch facts for the past 3 days."
    ),
    "health": Command("localtrace_health", "Print GET /health."),
    "recent-events": Command("localtrace_recent_events", "Print recent raw events."),
    "events-between": Command(
        "localtrace_events_between", "Print raw events in a range."
    ),
    "day-summary": Command("localtrace_day_summary", "Summarize one UTC day."),
    "explain-gap": Command("localtrace_explain_gap", "Explain an observed-time gap."),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="localtrace-skill",
        description="Invoke LocalTrace skill tools.",
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = COMMANDS[args.command]
    module = importlib.import_module(command.module)
    original_argv = sys.argv
    sys.argv = [f"localtrace-skill {args.command}", *args.args]
    try:
        return int(module.main())
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
