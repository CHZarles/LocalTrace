from __future__ import annotations

import argparse

from localtrace_http import (
    CORE_EVENT_CAP,
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    apply_event_limit,
    day_bounds,
    event_request_limit,
    events_between,
    fail,
    parse_date,
    parse_positive_int,
    print_json,
    summarize_day,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize one LocalTrace day from raw events."
    )
    add_base_url_argument(parser)
    parser.add_argument("--date", required=True)
    parser.add_argument("--limit", default="1000")
    args = parser.parse_args()

    try:
        day = parse_date(args.date)
        limit = parse_positive_int(args.limit, "--limit")
        start, end = day_bounds(day)
        request_limit = event_request_limit(limit)
        body = events_between(args.base_url, start, end, limit=request_limit)
        events, truncated = apply_event_limit(
            body.get("events", []), limit, request_limit=request_limit
        )
        if truncated:
            print_json(
                {
                    "ok": False,
                    "partial": True,
                    "error": "day summary exceeds event limit or core event cap",
                    "truncated": True,
                    "source_event_limit": limit,
                    "core_event_cap": CORE_EVENT_CAP,
                }
            )
            return 1
        summary = summarize_day(events, day)
        summary["truncated"] = truncated
        summary["source_event_limit"] = limit
        print_json(summary)
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
