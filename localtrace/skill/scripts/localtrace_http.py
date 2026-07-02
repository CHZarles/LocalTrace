from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, build_opener

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
CORE_EVENT_CAP = 5000


class LocalTraceError(Exception):
    pass


class LocalTraceValidationError(LocalTraceError):
    pass


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


HTTP_OPENER = build_opener(NoRedirectHandler)


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


def request_json(
    base_url: str, path: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    url = f"{base_url}{path}"
    if params:
        query = {key: value for key, value in params.items() if value is not None}
        url = f"{url}?{urlencode(query)}"

    try:
        with HTTP_OPENER.open(url, timeout=5) as response:
            body = json.loads(response.read())
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
    if not isinstance(body, dict):
        raise LocalTraceError(
            "LocalTrace request failed: expected JSON object response"
        )
    if body.get("ok") is False and isinstance(body.get("error"), str):
        raise LocalTraceError(f"LocalTrace request failed: {body['error']}")
    return body


def _read_error_detail(exc: HTTPError) -> str:
    try:
        body = json.loads(exc.read())
    except (json.JSONDecodeError, OSError):
        return exc.reason
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return str(body)


def parse_positive_int(value: str | int, label: str, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LocalTraceValidationError(f"{label} must be an integer") from exc
    if parsed < 1:
        raise LocalTraceValidationError(f"{label} must be at least 1")
    if maximum is not None and parsed > maximum:
        raise LocalTraceValidationError(f"{label} must be at most {maximum}")
    return parsed


def normalize_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "http":
        raise LocalTraceValidationError("base URL must use http")
    if parsed.hostname != "127.0.0.1":
        raise LocalTraceValidationError("base URL must use 127.0.0.1")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise LocalTraceValidationError(
            "base URL must not include a path, query, or fragment"
        )
    return base_url.rstrip("/")


def rfc3339_utc(value: str, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocalTraceValidationError(f"{label} must be RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LocalTraceValidationError(f"{label} must be RFC3339 UTC")
    return format_rfc3339_utc(parsed)


def rfc3339_utc_datetime(value: str, label: str) -> datetime:
    normalized = rfc3339_utc(value, label)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def format_rfc3339_utc(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LocalTraceValidationError("--date must be YYYY-MM-DD") from exc


def ensure_ordered_range(start: str, end: str) -> None:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if start_dt >= end_dt:
        raise LocalTraceValidationError("--from must be before --to")


def day_bounds(day: date) -> tuple[str, str]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return format_rfc3339_utc(start), format_rfc3339_utc(end)


def range_day_bounds(start: str, end: str) -> tuple[str, str]:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(UTC)
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(UTC)
    day_start = datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=UTC)
    day_end = datetime(end_dt.year, end_dt.month, end_dt.day, tzinfo=UTC) + timedelta(
        days=1
    )
    return format_rfc3339_utc(day_start), format_rfc3339_utc(day_end)


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


def events_from_response(body: dict[str, Any]) -> list[dict[str, Any]]:
    events = body.get("events", [])
    if not isinstance(events, list):
        raise LocalTraceError("LocalTrace request failed: events must be a JSON array")
    return events


def collect_events_between(
    base_url: str,
    start: str,
    end: str,
    *,
    limit: int,
    source: str | None = None,
    kind: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return _collect_events_between(
        base_url,
        start_dt,
        end_dt,
        limit=limit,
        source=source,
        kind=kind,
    )


def _collect_events_between(
    base_url: str,
    start: datetime,
    end: datetime,
    *,
    limit: int,
    source: str | None,
    kind: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    if limit < 1:
        return [], True

    request_limit = event_request_limit(limit)
    body = events_between(
        base_url,
        format_rfc3339_utc(start),
        format_rfc3339_utc(end),
        source=source,
        kind=kind,
        limit=request_limit,
    )
    events = events_from_response(body)
    if len(events) < request_limit:
        return events, False
    if len(events) > limit:
        return events[:limit], True
    if end - start <= timedelta(milliseconds=1):
        return events[:limit], True

    midpoint = start + (end - start) / 2
    left, left_partial = _collect_events_between(
        base_url,
        start,
        midpoint,
        limit=limit,
        source=source,
        kind=kind,
    )
    if left_partial:
        return left[:limit], True
    if len(left) >= limit:
        right_probe, right_partial = _collect_events_between(
            base_url,
            midpoint,
            end,
            limit=1,
            source=source,
            kind=kind,
        )
        return left[:limit], right_partial or bool(right_probe)
    right, right_partial = _collect_events_between(
        base_url,
        midpoint,
        end,
        limit=limit - len(left),
        source=source,
        kind=kind,
    )
    return [*left, *right], right_partial


def summarize_day(events: list[dict[str, Any]], day: date) -> dict[str, Any]:
    ordered = _sort_events(events)
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
        "by_source": _span_counts(ordered, "source"),
        "by_kind": _span_counts(ordered, "kind"),
        "by_entity": sorted(
            entities.values(),
            key=lambda item: (-int(item["count"]), item["entity_type"], item["entity"]),
        ),
    }


def apply_event_limit(
    events: list[dict[str, Any]], limit: int
) -> tuple[list[dict[str, Any]], bool]:
    if len(events) > limit:
        return events[:limit], True
    return events, False


def event_request_limit(limit: int) -> int:
    return min(limit + 1, CORE_EVENT_CAP)


def explain_gap(events: list[dict[str, Any]], start: str, end: str) -> dict[str, Any]:
    ordered = _sort_events(events)
    before = [event for event in ordered if str(event["observed_at"]) < start]
    inside = [event for event in ordered if start <= str(event["observed_at"]) < end]
    after = [event for event in ordered if str(event["observed_at"]) >= end]

    return gap_context_result(
        start,
        end,
        before[-1] if before else None,
        inside,
        after[0] if after else None,
    )


def gap_context_result(
    start: str,
    end: str,
    before: dict[str, Any] | None,
    inside: list[dict[str, Any]],
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    gap_seconds = _seconds_between(start, end)
    previous_delta = (
        _seconds_between(str(before["observed_at"]), start) if before else None
    )
    next_delta = _seconds_between(end, str(after["observed_at"])) if after else None
    return {
        "ok": True,
        "from": start,
        "to": end,
        "gap_detected": not inside,
        "inside_event_count": len(inside),
        "gap_seconds": gap_seconds,
        "previous_event_delta_seconds": previous_delta,
        "next_event_delta_seconds": next_delta,
        "before": before,
        "inside": inside,
        "after": after,
        "explanation": _gap_explanation(
            len(inside), gap_seconds, previous_delta, next_delta
        ),
    }


def _span_counts(events: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    spans: dict[str, dict[str, Any]] = {}
    for event in events:
        observed_at = str(event["observed_at"])
        key = str(event.get(field, ""))
        span = spans.setdefault(
            key,
            {
                "count": 0,
                "first_observed_at": observed_at,
                "last_observed_at": observed_at,
            },
        )
        span["count"] += 1
        span["last_observed_at"] = observed_at
    return dict(sorted(spans.items()))


def _gap_explanation(
    inside_count: int,
    gap_seconds: int,
    previous_delta: int | None,
    next_delta: int | None,
) -> str:
    if inside_count:
        return (
            f"{inside_count} stored event(s) were observed in this "
            f"{gap_seconds}-second window; nearest context is included for "
            "sparse-window review."
        )
    if previous_delta is not None and next_delta is not None:
        return (
            f"No stored events were observed in this {gap_seconds}-second window; "
            f"nearest context events are {previous_delta} seconds before and "
            f"{next_delta} seconds after."
        )
    if previous_delta is not None:
        return (
            f"No stored events were observed in this {gap_seconds}-second window; "
            f"the nearest context event is {previous_delta} seconds before."
        )
    if next_delta is not None:
        return (
            f"No stored events were observed in this {gap_seconds}-second window; "
            f"the nearest context event is {next_delta} seconds after."
        )
    return (
        f"No stored events were observed in this {gap_seconds}-second window, "
        "and no context events were found."
    )


def _seconds_between(start: str, end: str) -> int:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return int((end_dt - start_dt).total_seconds())


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events, key=lambda event: (str(event["observed_at"]), int(event["id"]))
    )
