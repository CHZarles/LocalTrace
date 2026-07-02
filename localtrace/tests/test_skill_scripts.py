import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skill" / "scripts"


class FakeLocalTraceServer:
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes
        self.requests: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FakeLocalTraceServer":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(self.path)
                route = owner.routes.get(urlparse(self.path).path)
                if route is None:
                    self._write_json(404, {"ok": False, "error": "not found"})
                    return
                body = route["body"]
                if callable(body):
                    body = body(self.path)
                self._write_json(
                    route.get("status", 200), body, route.get("headers", {})
                )

            def log_message(self, format: str, *args: object) -> None:
                return

            def _write_json(
                self,
                status: int,
                body: dict[str, Any],
                headers: dict[str, str] | None = None,
            ) -> None:
                encoded = json.dumps(body).encode("utf-8")
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler


def run_script(
    script_name: str, args: list[str], base_url: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if base_url is not None:
        env["LOCALTRACE_BASE_URL"] = base_url
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *args],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def output_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(result.stdout)


def parse_request(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlparse(path)
    return parsed.path, parse_qs(parsed.query)


def sample_events() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "observed_at": "2026-07-01T09:00:00.000Z",
            "received_at": "2026-07-01T09:00:01.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": None,
            "payload": {"activity": "focus"},
        },
        {
            "id": 2,
            "observed_at": "2026-07-01T09:30:00.000Z",
            "received_at": "2026-07-01T09:30:01.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "github.com",
            "title": None,
            "payload": {"activity": "focus"},
        },
        {
            "id": 3,
            "observed_at": "2026-07-01T10:00:00.000Z",
            "received_at": "2026-07-01T10:00:01.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": None,
            "payload": {"activity": "focus"},
        },
    ]


def events_route(events: list[dict[str, Any]]):
    def route(path: str) -> dict[str, Any]:
        _request_path, query = parse_request(path)
        selected = events
        if "from" in query:
            selected = [
                event for event in selected if event["observed_at"] >= query["from"][0]
            ]
        if "to" in query:
            selected = [
                event for event in selected if event["observed_at"] < query["to"][0]
            ]
        selected = sorted(
            selected,
            key=lambda event: (event["observed_at"], event["id"]),
        )
        if "limit" in query:
            selected = selected[: int(query["limit"][0])]
        return {"ok": True, "events": selected}

    return route


def test_health_script_returns_core_health_json() -> None:
    with FakeLocalTraceServer(
        {"/health": {"body": {"ok": True, "service": "localtrace"}}}
    ) as server:
        result = run_script("localtrace_health.py", [], server.base_url)

    assert result.returncode == 0
    assert output_json(result) == {"ok": True, "service": "localtrace"}
    assert server.requests == ["/health"]


def test_recent_events_script_scans_backward_from_requested_end() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(sample_events())}}
    ) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "2",
                "--scan-limit",
                "5",
                "--to",
                "2026-07-02T00:00:00.000Z",
                "--lookback-days",
                "2",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["events"] == sample_events()[-2:]
    assert body["recent_limit"] == 2
    assert body["scan_limit"] == 5
    assert body["search_from"] == "2026-07-01T00:00:00.000Z"
    assert body["search_to"] == "2026-07-02T00:00:00.000Z"
    assert body["windows_scanned"] == 1
    assert body["truncated"] is False
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["from"] == ["2026-07-01T00:00:00.000Z"]
    assert query["to"] == ["2026-07-02T00:00:00.000Z"]
    assert query["limit"] == ["6"]


def test_recent_events_refuses_partial_window_when_scan_limit_is_exceeded() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(sample_events())}}
    ) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "2",
                "--scan-limit",
                "2",
                "--to",
                "2026-07-02T00:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    assert output_json(result) == {
        "ok": False,
        "partial": True,
        "error": "recent events window exceeds scan limit; increase --scan-limit",
        "truncated": True,
        "scan_limit": 2,
        "window_from": "2026-07-01T00:00:00.000Z",
        "window_to": "2026-07-02T00:00:00.000Z",
    }
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["3"]


def test_recent_events_rejects_scan_limit_above_detection_cap() -> None:
    result = run_script("localtrace_recent_events.py", ["--scan-limit", "5000"])

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "--scan-limit must be at most 4999",
    }


def test_events_between_script_validates_range_and_filters() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": [sample_events()[0]]}}}
    ) as server:
        result = run_script(
            "localtrace_events_between.py",
            [
                "--from",
                "2026-07-01T09:00:00.000Z",
                "--to",
                "2026-07-01T10:00:00.000Z",
                "--source",
                "windows_probe",
                "--kind",
                "app_active",
                "--limit",
                "10",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    assert output_json(result)["events"] == [sample_events()[0]]
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["from"] == ["2026-07-01T09:00:00.000Z"]
    assert query["to"] == ["2026-07-01T10:00:00.000Z"]
    assert query["source"] == ["windows_probe"]
    assert query["kind"] == ["app_active"]
    assert query["limit"] == ["10"]


def test_events_between_script_rejects_invalid_timestamp_without_http_call() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": []}}}
    ) as server:
        result = run_script(
            "localtrace_events_between.py",
            [
                "--from",
                "2026-07-01 09:00",
                "--to",
                "2026-07-01T10:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "--from must be RFC3339 UTC",
    }
    assert server.requests == []


def test_recent_events_script_returns_json_for_invalid_limit() -> None:
    result = run_script("localtrace_recent_events.py", ["--limit", "0"])

    assert result.returncode == 2
    assert output_json(result) == {"ok": False, "error": "--limit must be at least 1"}


def test_day_summary_script_derives_counts_and_observed_spans() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": sample_events()}}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py", ["--date", "2026-07-01"], server.base_url
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["date"] == "2026-07-01"
    assert body["event_count"] == 3
    assert body["observed_start"] == "2026-07-01T09:00:00.000Z"
    assert body["observed_end"] == "2026-07-01T10:00:00.000Z"
    assert body["by_source"] == {
        "browser_extension": {
            "count": 1,
            "first_observed_at": "2026-07-01T09:30:00.000Z",
            "last_observed_at": "2026-07-01T09:30:00.000Z",
        },
        "windows_probe": {
            "count": 2,
            "first_observed_at": "2026-07-01T09:00:00.000Z",
            "last_observed_at": "2026-07-01T10:00:00.000Z",
        },
    }
    assert body["by_kind"] == {
        "app_active": {
            "count": 2,
            "first_observed_at": "2026-07-01T09:00:00.000Z",
            "last_observed_at": "2026-07-01T10:00:00.000Z",
        },
        "tab_active": {
            "count": 1,
            "first_observed_at": "2026-07-01T09:30:00.000Z",
            "last_observed_at": "2026-07-01T09:30:00.000Z",
        },
    }
    assert body["by_entity"][0] == {
        "entity_type": "app",
        "entity": "Code.exe",
        "count": 2,
        "first_observed_at": "2026-07-01T09:00:00.000Z",
        "last_observed_at": "2026-07-01T10:00:00.000Z",
    }
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["from"] == ["2026-07-01T00:00:00.000Z"]
    assert query["to"] == ["2026-07-02T00:00:00.000Z"]


def test_explain_gap_script_reports_before_inside_and_after_context() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(sample_events())}}
    ) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:20:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["gap_detected"] is True
    assert body["inside_event_count"] == 0
    assert body["before"]["id"] == 1
    assert body["after"]["id"] == 2
    assert body["gap_seconds"] == 600
    assert body["previous_event_delta_seconds"] == 600
    assert body["next_event_delta_seconds"] == 600
    assert body["explanation"] == (
        "No stored events were observed in this 600-second window; "
        "nearest same-day events are 600 seconds before and 600 seconds after."
    )
    assert len(server.requests) == 3
    before_path, before_query = parse_request(server.requests[1])
    assert before_path == "/events"
    assert before_query["to"] == ["2026-07-01T09:10:00.000Z"]
    assert before_query["limit"] == ["1001"]
    after_path, after_query = parse_request(server.requests[2])
    assert after_path == "/events"
    assert after_query["from"] == ["2026-07-01T09:20:00.000Z"]
    assert after_query["limit"] == ["1"]


def test_scripts_return_machine_readable_error_when_core_is_unavailable() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "http://127.0.0.1:1"])

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert "LocalTrace request failed" in body["error"]


def test_health_script_uses_env_base_url_override() -> None:
    with FakeLocalTraceServer(
        {"/health": {"body": {"ok": True, "service": "localtrace"}}}
    ) as server:
        result = run_script("localtrace_health.py", [], server.base_url)

    assert result.returncode == 0
    assert output_json(result)["service"] == "localtrace"
    assert server.requests == ["/health"]


def test_http_helper_does_not_follow_redirects() -> None:
    with FakeLocalTraceServer(
        {
            "/health": {
                "status": 302,
                "headers": {"Location": "http://example.com/health"},
                "body": {"ok": False, "error": "redirect"},
            }
        }
    ) as server:
        result = run_script("localtrace_health.py", [], server.base_url)

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert "HTTP 302" in body["error"]


def test_scripts_reject_non_loopback_base_url_before_http_request() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "http://example.com"])

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "base URL must use a loopback host",
    }


def test_scripts_reject_https_base_url_before_http_request() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "https://localhost"])

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "base URL must use http",
    }


def test_day_summary_refuses_partial_output_when_event_limit_is_exceeded() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": sample_events()}}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py",
            ["--date", "2026-07-01", "--limit", "2"],
            server.base_url,
        )

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert body["partial"] is True
    assert body["error"] == "day summary exceeds event limit; increase --limit"
    assert body["truncated"] is True
    assert body["source_event_limit"] == 2
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["3"]


def test_day_summary_rejects_limit_above_detection_cap() -> None:
    result = run_script(
        "localtrace_day_summary.py", ["--date", "2026-07-01", "--limit", "5000"]
    )

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "--limit must be at most 4999",
    }


def test_explain_gap_refuses_partial_output_when_event_limit_is_exceeded() -> None:
    crowded_events = [
        {
            **sample_events()[0],
            "id": index + 10,
            "observed_at": f"2026-07-01T09:1{index}:00.000Z",
            "entity": f"app-{index}.exe",
        }
        for index in range(3)
    ]
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(crowded_events)}}
    ) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:13:00.000Z",
                "--limit",
                "2",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert body["partial"] is True
    assert body["error"] == "gap explanation exceeds event limit; increase --limit"
    assert body["truncated"] is True
    assert body["source_event_limit"] == 2
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["3"]


def test_skill_scripts_do_not_import_core_or_sqlite() -> None:
    script_paths = sorted(SCRIPTS_DIR.glob("*.py"))

    assert script_paths
    for script_path in script_paths:
        text = script_path.read_text(encoding="utf-8")
        assert "localtrace_core" not in text
        assert "sqlite3" not in text
