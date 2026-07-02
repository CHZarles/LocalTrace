from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    ensure_ordered_range,
    events_between,
    fail,
    parse_positive_int,
    print_json,
    rfc3339_utc,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print LocalTrace events in a range.")
    add_base_url_argument(parser)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--source")
    parser.add_argument("--kind")
    parser.add_argument("--limit", default="200")
    args = parser.parse_args()

    try:
        start = rfc3339_utc(args.start, "--from")
        end = rfc3339_utc(args.end, "--to")
        ensure_ordered_range(start, end)
        limit = parse_positive_int(args.limit, "--limit")
        print_json(
            events_between(
                args.base_url,
                start,
                end,
                source=args.source,
                kind=args.kind,
                limit=limit,
            )
        )
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
