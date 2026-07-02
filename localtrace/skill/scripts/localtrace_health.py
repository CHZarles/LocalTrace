from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    fail,
    print_json,
    request_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print LocalTrace health JSON.")
    add_base_url_argument(parser)
    args = parser.parse_args()

    try:
        print_json(request_json(args.base_url, "/health"))
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
