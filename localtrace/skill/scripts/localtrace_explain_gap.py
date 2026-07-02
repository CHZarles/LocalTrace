from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any

from localtrace_http import (
    CORE_EVENT_CAP,
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    apply_event_limit,
    ensure_ordered_range,
    event_request_limit,
    events_between,
    fail,
    format_rfc3339_utc,
    gap_context_result,
    parse_positive_int,
    print_json,
    rfc3339_utc,
    rfc3339_utc_datetime,
)


def _first_or_none(events: list[dict]) -> dict | None:
    return events[0] if events else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explain a LocalTrace observed-time gap from nearby events."
    )
    add_base_url_argument(parser)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--limit", default="1000")
    parser.add_argument("--context-days", default="1")
    args = parser.parse_args()

    try:
        start = rfc3339_utc(args.start, "--from")
        end = rfc3339_utc(args.end, "--to")
        ensure_ordered_range(start, end)
        limit = parse_positive_int(args.limit, "--limit")
        context_days = parse_positive_int(
            args.context_days, "--context-days", maximum=30
        )
        inside_request_limit = event_request_limit(limit)
        inside_body = events_between(
            args.base_url, start, end, limit=inside_request_limit
        )
        inside, inside_truncated = apply_event_limit(
            inside_body.get("events", []),
            limit,
            request_limit=inside_request_limit,
        )
        if inside_truncated:
            print_json(
                {
                    "ok": False,
                    "partial": True,
                    "error": "gap explanation exceeds event limit or core event cap",
                    "truncated": True,
                    "source_event_limit": limit,
                    "core_event_cap": CORE_EVENT_CAP,
                }
            )
            return 1
        before, before_context_truncated = _nearest_before(
            args.base_url,
            rfc3339_utc_datetime(start, "--from"),
            context_days=context_days,
            limit=limit,
        )
        after_end = format_rfc3339_utc(
            rfc3339_utc_datetime(end, "--to") + timedelta(days=context_days)
        )
        after_body = events_between(args.base_url, end, after_end, limit=1)
        result = gap_context_result(
            start,
            end,
            before,
            inside,
            _first_or_none(after_body.get("events", [])),
        )
        result["truncated"] = False
        result["source_event_limit"] = limit
        result["context_days"] = context_days
        result["before_context_truncated"] = before_context_truncated
        result["before_context_exact"] = not before_context_truncated
        print_json(result)
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


def _nearest_before(
    base_url: str,
    start: datetime,
    *,
    context_days: int,
    limit: int,
) -> tuple[dict[str, Any] | None, bool]:
    earliest = start - timedelta(days=context_days)
    return _nearest_before_between(base_url, earliest, start, limit=limit)


def _nearest_before_between(
    base_url: str,
    window_start: datetime,
    window_end: datetime,
    *,
    limit: int,
) -> tuple[dict[str, Any] | None, bool]:
    request_limit = event_request_limit(limit)
    body = events_between(
        base_url,
        format_rfc3339_utc(window_start),
        format_rfc3339_utc(window_end),
        limit=request_limit,
    )
    events, truncated = apply_event_limit(
        body.get("events", []), limit, request_limit=request_limit
    )
    if not truncated:
        return events[-1] if events else None, False

    if window_end - window_start <= timedelta(milliseconds=1):
        return events[-1] if events else None, True

    midpoint = window_start + (window_end - window_start) / 2
    nearest, nearest_truncated = _nearest_before_between(
        base_url, midpoint, window_end, limit=limit
    )
    if nearest is not None:
        return nearest, nearest_truncated
    return _nearest_before_between(base_url, window_start, midpoint, limit=limit)


if __name__ == "__main__":
    raise SystemExit(main())
