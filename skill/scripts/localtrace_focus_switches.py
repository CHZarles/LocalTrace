from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import Any

from localtrace_http import (
    CORE_EVENT_CAP,
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    events_between,
    events_from_response,
    fail,
    format_rfc3339_utc,
    print_json,
    request_json,
    rfc3339_utc_datetime,
)

FOCUS_KINDS = {"app_active", "tab_active"}
DEFAULT_DAYS = 3
DEFAULT_IDLE_CUTOFF_SECONDS = 300


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report LocalTrace focus-switch facts for the past 3 days."
    )
    add_base_url_argument(parser)
    parser.add_argument("--to")
    args = parser.parse_args()

    try:
        end = _end_time(args.to)
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)

    start = end - timedelta(days=DEFAULT_DAYS)
    start_text = format_rfc3339_utc(start)
    end_text = format_rfc3339_utc(end)

    idle_cutoff_seconds = _idle_cutoff_seconds(args.base_url)
    try:
        body = events_between(
            args.base_url,
            start_text,
            end_text,
            limit=CORE_EVENT_CAP,
        )
        events = events_from_response(body)
    except LocalTraceError as exc:
        return fail(str(exc))

    print_json(
        focus_switch_facts(
            events,
            start_text,
            end_text,
            idle_cutoff_seconds=idle_cutoff_seconds,
        )
    )
    return 0


def _end_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return rfc3339_utc_datetime(value, "--to")


def _idle_cutoff_seconds(base_url: str) -> int:
    try:
        body = request_json(base_url, "/settings")
    except LocalTraceError:
        return DEFAULT_IDLE_CUTOFF_SECONDS
    settings = body.get("settings")
    capture = settings.get("capture") if isinstance(settings, dict) else None
    value = capture.get("idle_cutoff_seconds") if isinstance(capture, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 300


def focus_switch_facts(
    events: list[dict[str, Any]],
    start: str,
    end: str,
    *,
    idle_cutoff_seconds: int,
) -> dict[str, Any]:
    focus_events = [
        event for event in _sort_events(events) if event.get("kind") in FOCUS_KINDS
    ]
    durations: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    switches: list[dict[str, Any]] = []
    unknown_or_idle_seconds = 0.0
    long_gap_count = 0

    for event in focus_events:
        target = _target(event)
        item = durations.setdefault(
            _target_key(target),
            {**target, "event_count": 0, "duration_seconds": 0.0},
        )
        item["event_count"] += 1

    for current, following in zip(focus_events, focus_events[1:], strict=False):
        current_target = _target(current)
        following_target = _target(following)
        gap_seconds = _seconds_between(
            str(current["observed_at"]), str(following["observed_at"])
        )
        attributed_seconds = min(gap_seconds, idle_cutoff_seconds)
        if gap_seconds > idle_cutoff_seconds:
            long_gap_count += 1
            unknown_or_idle_seconds += gap_seconds - idle_cutoff_seconds
        durations[_target_key(current_target)]["duration_seconds"] += attributed_seconds
        if _target_key(current_target) != _target_key(following_target):
            switches.append(
                {
                    "at": str(following["observed_at"]),
                    "from": current_target,
                    "to": following_target,
                    "gap_seconds": _rounded_seconds(gap_seconds),
                }
            )

    target_durations = sorted(
        (
            {
                **item,
                "duration_seconds": _rounded_seconds(item["duration_seconds"]),
            }
            for item in durations.values()
        ),
        key=lambda item: (
            -float(item["duration_seconds"]),
            -int(item["event_count"]),
            str(item["entity_type"]),
            str(item["entity"]),
            str(item.get("title", "")),
        ),
    )

    return {
        "ok": True,
        "from": start,
        "to": end,
        "window_days": DEFAULT_DAYS,
        "idle_cutoff_seconds": idle_cutoff_seconds,
        "focus_event_count": len(focus_events),
        "focus_target_count": len(durations),
        "switch_count": len(switches),
        "unknown_or_idle_seconds": _rounded_seconds(unknown_or_idle_seconds),
        "long_gap_count": long_gap_count,
        "title_capture": _title_capture(focus_events),
        "target_durations": target_durations,
        "switches": switches,
        "prompt_context": {
            "focus_target": (
                "entity_type + entity + title when title is present; "
                "otherwise entity_type + entity"
            ),
            "title_capture": (
                "windows_probe app_active events support title when the "
                "runtime captures it. Use title_capture counts and raw events "
                "to describe current data. Do not conclude that windows_probe "
                "cannot track titles solely because current samples have null "
                "title; report that current captured data has no Windows app "
                "titles and check runtime version, restart state, and "
                "capture.store_titles."
            ),
            "duration_rule": (
                "time until the next focus event is attributed to the current "
                "target up to idle_cutoff_seconds; the excess is "
                "unknown_or_idle_seconds"
            ),
            "evaluation": (
                "Use these factual fields with the user's prompt for any AI judgment."
            ),
        },
    }


def _target(event: dict[str, Any]) -> dict[str, str]:
    target = {
        "entity_type": str(event.get("entity_type", "")),
        "entity": str(event.get("entity", "")),
    }
    title = event.get("title")
    if isinstance(title, str) and title:
        target["title"] = title
    return target


def _title_capture(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "browser_extension": _title_capture_for_source(events, "browser_extension"),
        "windows_probe": _title_capture_for_source(events, "windows_probe"),
    }


def _title_capture_for_source(
    events: list[dict[str, Any]], source: str
) -> dict[str, Any]:
    source_events = [event for event in events if event.get("source") == source]
    examples: list[dict[str, str]] = []
    seen_titles: set[tuple[str, str, str]] = set()
    with_title_count = 0

    for event in source_events:
        title = event.get("title")
        if not isinstance(title, str) or not title:
            continue

        with_title_count += 1
        example_key = (
            str(event.get("entity_type", "")),
            str(event.get("entity", "")),
            title,
        )
        if example_key in seen_titles:
            continue
        seen_titles.add(example_key)
        if len(examples) >= 5:
            continue
        examples.append(
            {
                "observed_at": str(event.get("observed_at", "")),
                "entity_type": example_key[0],
                "entity": example_key[1],
                "title": title,
            }
        )

    return {
        "focus_event_count": len(source_events),
        "with_title_count": with_title_count,
        "without_title_count": len(source_events) - with_title_count,
        "title_examples": examples,
    }


def _target_key(target: dict[str, str]) -> tuple[str, str, str | None]:
    return (target["entity_type"], target["entity"], target.get("title"))


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events, key=lambda event: (str(event.get("observed_at", "")), _id(event))
    )


def _id(event: dict[str, Any]) -> int:
    value = event.get("id", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _seconds_between(start: str, end: str) -> float:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (end_dt - start_dt).total_seconds()


def _rounded_seconds(value: float) -> int | float:
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


if __name__ == "__main__":
    raise SystemExit(main())
