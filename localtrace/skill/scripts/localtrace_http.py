from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class LocalTraceError(Exception):
    pass


def add_base_url_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LOCALTRACE_BASE_URL", DEFAULT_BASE_URL),
        help="LocalTrace core base URL",
    )


def print_json(body: dict[str, Any]) -> None:
    print(json.dumps(body, sort_keys=True))


def fail(message: str, code: int = 1) -> int:
    print_json({"ok": False, "error": message})
    return code


def request_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        query = {key: value for key, value in params.items() if value is not None}
        url = f"{url}?{urlencode(query)}"

    try:
        with urlopen(url, timeout=5) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = _read_error_detail(exc)
        raise LocalTraceError(
            f"LocalTrace request failed: HTTP {exc.code}: {detail}"
        ) from exc
    except (OSError, URLError) as exc:
        raise LocalTraceError(f"LocalTrace request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LocalTraceError(
            "LocalTrace request failed: invalid JSON response"
        ) from exc


def _read_error_detail(exc: HTTPError) -> str:
    try:
        body = json.loads(exc.read())
    except (json.JSONDecodeError, OSError):
        return exc.reason
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return str(body)


def parse_positive_int(value: str | int, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LocalTraceError(f"{label} must be an integer") from exc
    if parsed < 1:
        raise LocalTraceError(f"{label} must be at least 1")
    return parsed


def rfc3339_utc(value: str, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocalTraceError(f"{label} must be RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LocalTraceError(f"{label} must be RFC3339 UTC")
    return _format_rfc3339_utc(parsed)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LocalTraceError("--date must be YYYY-MM-DD") from exc


def ensure_ordered_range(start: str, end: str) -> None:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if start_dt >= end_dt:
        raise LocalTraceError("--from must be before --to")


def day_bounds(day: date) -> tuple[str, str]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return _format_rfc3339_utc(start), _format_rfc3339_utc(end)


def range_day_bounds(start: str, end: str) -> tuple[str, str]:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(UTC)
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(UTC)
    day_start = datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=UTC)
    day_end = datetime(end_dt.year, end_dt.month, end_dt.day, tzinfo=UTC) + timedelta(
        days=1
    )
    return _format_rfc3339_utc(day_start), _format_rfc3339_utc(day_end)


def events_between(
    base_url: str,
    start: str,
    end: str,
    *,
    source: str | None = None,
    kind: str | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    return request_json(
        base_url,
        "/events",
        {
            "from": start,
            "to": end,
            "source": source,
            "kind": kind,
            "limit": limit,
        },
    )


def summarize_day(events: list[dict[str, Any]], day: date) -> dict[str, Any]:
    ordered = _sort_events(events)
    by_source = Counter(str(event.get("source", "")) for event in ordered)
    by_kind = Counter(str(event.get("kind", "")) for event in ordered)
    entities: dict[tuple[str, str], dict[str, Any]] = {}

    for event in ordered:
        observed_at = str(event["observed_at"])
        key = (str(event.get("entity_type", "")), str(event.get("entity", "")))
        entity = entities.setdefault(
            key,
            {
                "entity_type": key[0],
                "entity": key[1],
                "count": 0,
                "first_observed_at": observed_at,
                "last_observed_at": observed_at,
            },
        )
        entity["count"] += 1
        entity["last_observed_at"] = observed_at

    return {
        "ok": True,
        "date": day.isoformat(),
        "event_count": len(ordered),
        "observed_start": ordered[0]["observed_at"] if ordered else None,
        "observed_end": ordered[-1]["observed_at"] if ordered else None,
        "by_source": dict(sorted(by_source.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "by_entity": sorted(
            entities.values(),
            key=lambda item: (-int(item["count"]), item["entity_type"], item["entity"]),
        ),
    }


def explain_gap(events: list[dict[str, Any]], start: str, end: str) -> dict[str, Any]:
    ordered = _sort_events(events)
    before = [event for event in ordered if str(event["observed_at"]) < start]
    inside = [event for event in ordered if start <= str(event["observed_at"]) < end]
    after = [event for event in ordered if str(event["observed_at"]) >= end]

    if inside:
        explanation = "Stored events were observed in this window."
    else:
        explanation = "No stored events were observed in this window."

    return {
        "ok": True,
        "from": start,
        "to": end,
        "gap_detected": not inside,
        "inside_event_count": len(inside),
        "before": before[-1] if before else None,
        "inside": inside,
        "after": after[0] if after else None,
        "explanation": explanation,
    }


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events, key=lambda event: (str(event["observed_at"]), int(event["id"]))
    )


def _format_rfc3339_utc(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
