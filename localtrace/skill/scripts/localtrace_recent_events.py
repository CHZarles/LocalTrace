from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    fail,
    parse_positive_int,
    print_json,
    request_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print recent LocalTrace events.")
    add_base_url_argument(parser)
    parser.add_argument("--limit", default="25")
    args = parser.parse_args()

    try:
        limit = parse_positive_int(args.limit, "--limit")
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)

    try:
        print_json(request_json(args.base_url, "/events", {"limit": limit}))
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
