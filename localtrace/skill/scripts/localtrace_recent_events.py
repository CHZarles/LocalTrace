from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    apply_event_limit,
    fail,
    parse_positive_int,
    print_json,
    request_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print recent LocalTrace events.")
    add_base_url_argument(parser)
    parser.add_argument("--limit", default="25")
    parser.add_argument("--scan-limit", default="1000")
    args = parser.parse_args()

    try:
        limit = parse_positive_int(args.limit, "--limit")
        scan_limit = parse_positive_int(args.scan_limit, "--scan-limit")
        if scan_limit < limit:
            raise LocalTraceValidationError("--scan-limit must be at least --limit")
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)

    try:
        body = request_json(args.base_url, "/events", {"limit": scan_limit + 1})
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    events, truncated = apply_event_limit(body.get("events", []), scan_limit)
    if truncated:
        print_json(
            {
                "ok": False,
                "partial": True,
                "error": "recent events exceed scan limit; increase --scan-limit",
                "truncated": True,
                "scan_limit": scan_limit,
            }
        )
        return 1
    print_json(
        {
            "ok": True,
            "events": events[-limit:],
            "recent_limit": limit,
            "scan_limit": scan_limit,
            "truncated": False,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
