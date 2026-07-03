from __future__ import annotations

import argparse
import webbrowser

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    fail,
    normalize_base_url,
    print_json,
    request_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the LocalTrace Web UI.")
    add_base_url_argument(parser)
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        base_url = normalize_base_url(args.base_url)
        health = request_json(base_url, "/health")
        dashboard_url = f"{base_url}/"
        opened = False if args.no_open else open_dashboard(dashboard_url)
        if not args.no_open and not opened:
            return fail("failed to open LocalTrace dashboard")
        print_json(
            {
                "ok": True,
                "dashboard_url": dashboard_url,
                "opened": opened,
                "health": health,
            }
        )
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


def open_dashboard(dashboard_url: str) -> bool:
    return bool(webbrowser.open(dashboard_url, new=2))


if __name__ == "__main__":
    raise SystemExit(main())
