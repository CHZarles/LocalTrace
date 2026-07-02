from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import Any

from localtrace_http import (
    CORE_EVENT_CAP,
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    apply_event_limit,
    event_request_limit,
    events_between,
    fail,
    format_rfc3339_utc,
    parse_positive_int,
    print_json,
    rfc3339_utc_datetime,
)

MAX_LOOKBACK_DAYS = 3660


def main() -> int:
    parser = argparse.ArgumentParser(description="Print recent LocalTrace events.")
    add_base_url_argument(parser)
    parser.add_argument("--limit", default="25")
    parser.add_argument("--scan-limit", default=str(CORE_EVENT_CAP))
    parser.add_argument("--lookback-days", default="30")
    parser.add_argument("--to")
    args = parser.parse_args()

    try:
        limit = parse_positive_int(args.limit, "--limit")
        scan_limit = parse_positive_int(args.scan_limit, "--scan-limit")
        lookback_days = parse_positive_int(
            args.lookback_days, "--lookback-days", maximum=MAX_LOOKBACK_DAYS
        )
        search_to = _search_to(args.to)
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)

    try:
        result = _scan_recent_events(
            args.base_url,
            search_to=search_to,
            limit=limit,
            scan_limit=scan_limit,
            lookback_days=lookback_days,
        )
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    if result["truncated"]:
        print_json(result)
        return 1
    print_json(
        {
            "ok": True,
            "events": result["events"],
            "recent_limit": limit,
            "scan_limit": scan_limit,
            "lookback_days": lookback_days,
            "windows_scanned": result["windows_scanned"],
            "search_from": result["search_from"],
            "search_to": format_rfc3339_utc(search_to),
            "lookback_exhausted": result["lookback_exhausted"],
            "truncated": False,
        }
    )
    return 0


def _search_to(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return rfc3339_utc_datetime(value, "--to")


def _scan_recent_events(
    base_url: str,
    *,
    search_to: datetime,
    limit: int,
    scan_limit: int,
    lookback_days: int,
) -> dict[str, Any]:
    collected: list[dict[str, Any]] = []
    window_end = search_to
    search_from = search_to
    windows_scanned = 0

    for _index in range(lookback_days):
        window_start = window_end - timedelta(days=1)
        window_from_text = format_rfc3339_utc(window_start)
        window_to_text = format_rfc3339_utc(window_end)
        request_limit = event_request_limit(scan_limit)
        body = events_between(
            base_url,
            window_from_text,
            window_to_text,
            limit=request_limit,
        )
        events, truncated = apply_event_limit(
            body.get("events", []), scan_limit, request_limit=request_limit
        )
        if truncated:
            return {
                "ok": False,
                "partial": True,
                "error": ("recent events window exceeds scan limit or core event cap"),
                "truncated": True,
                "scan_limit": scan_limit,
                "core_event_cap": CORE_EVENT_CAP,
                "window_from": window_from_text,
                "window_to": window_to_text,
            }
        collected.extend(events)
        search_from = window_start
        windows_scanned += 1
        if len(collected) >= limit:
            break
        window_end = window_start

    ordered = sorted(
        collected, key=lambda event: (str(event["observed_at"]), int(event["id"]))
    )
    return {
        "events": ordered[-limit:],
        "truncated": False,
        "windows_scanned": windows_scanned,
        "search_from": format_rfc3339_utc(search_from),
        "lookback_exhausted": windows_scanned >= lookback_days and len(ordered) < limit,
    }


if __name__ == "__main__":
    raise SystemExit(main())
