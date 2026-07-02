from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    apply_event_limit,
    ensure_ordered_range,
    events_between,
    explain_gap,
    fail,
    parse_positive_int,
    print_json,
    range_day_bounds,
    rfc3339_utc,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explain a LocalTrace observed-time gap from nearby events."
    )
    add_base_url_argument(parser)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--limit", default="1000")
    args = parser.parse_args()

    try:
        start = rfc3339_utc(args.start, "--from")
        end = rfc3339_utc(args.end, "--to")
        ensure_ordered_range(start, end)
        limit = parse_positive_int(args.limit, "--limit")
        query_start, query_end = range_day_bounds(start, end)
        body = events_between(args.base_url, query_start, query_end, limit=limit + 1)
        events, truncated = apply_event_limit(body.get("events", []), limit)
        if truncated:
            print_json(
                {
                    "ok": False,
                    "partial": True,
                    "error": "gap explanation exceeds event limit; increase --limit",
                    "truncated": True,
                    "source_event_limit": limit,
                }
            )
            return 1
        result = explain_gap(events, start, end)
        result["truncated"] = truncated
        result["source_event_limit"] = limit
        print_json(result)
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
