from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    add_base_url_argument,
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
        body = events_between(args.base_url, query_start, query_end, limit=limit)
        print_json(explain_gap(body.get("events", []), start, end))
    except LocalTraceError as exc:
        return fail(str(exc), code=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
