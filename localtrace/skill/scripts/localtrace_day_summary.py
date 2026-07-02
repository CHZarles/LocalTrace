from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    add_base_url_argument,
    day_bounds,
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
        body = events_between(args.base_url, start, end, limit=limit)
        print_json(summarize_day(body.get("events", []), day))
    except LocalTraceError as exc:
        return fail(str(exc), code=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
