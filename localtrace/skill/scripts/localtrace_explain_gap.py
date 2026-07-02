from __future__ import annotations

import argparse

from localtrace_http import (
    LocalTraceError,
    LocalTraceValidationError,
    add_base_url_argument,
    apply_event_limit,
    day_bounds,
    ensure_ordered_range,
    events_between,
    fail,
    parse_date,
    parse_positive_int,
    print_json,
    rfc3339_utc,
)


def _first_or_none(events: list[dict]) -> dict | None:
    return events[0] if events else None


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
        inside_body = events_between(args.base_url, start, end, limit=limit + 1)
        inside, inside_truncated = apply_event_limit(
            inside_body.get("events", []), limit
        )
        if inside_truncated:
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
        day_start, _day_end = day_bounds(parse_date(start[:10]))
        before_body = events_between(
            args.base_url, day_start, start, limit=1, order="desc"
        )
        _after_start, day_end = day_bounds(parse_date(end[:10]))
        after_body = events_between(args.base_url, end, day_end, limit=1)
        if inside:
            explanation = "Stored events were observed in this window."
        else:
            explanation = "No stored events were observed in this window."
        result = {
            "ok": True,
            "from": start,
            "to": end,
            "gap_detected": not inside,
            "inside_event_count": len(inside),
            "before": _first_or_none(before_body.get("events", [])),
            "inside": inside,
            "after": _first_or_none(after_body.get("events", [])),
            "explanation": explanation,
            "truncated": False,
            "source_event_limit": limit,
        }
        print_json(result)
    except LocalTraceValidationError as exc:
        return fail(str(exc), code=2)
    except LocalTraceError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
