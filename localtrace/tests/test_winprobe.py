import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from localtrace_winprobe.probe import (
    ForegroundApp,
    ProbeSettings,
    ProbeState,
    _parse_args,
    _settings_from_args,
    build_app_active_event,
    post_event,
)


def test_build_app_active_event_uses_core_schema_and_privacy_defaults() -> None:
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    foreground = ForegroundApp(
        pid=1234,
        title="Sensitive project title",
        exe_path=r"C:\Users\charles\AppData\Local\Programs\Code.exe",
    )

    event = build_app_active_event(
        foreground,
        observed_at=observed_at,
        settings=ProbeSettings(),
        seq=7,
    )

    assert event == {
        "observed_at": "2026-07-01T10:30:00.000Z",
        "source": "windows_probe",
        "seq": 7,
        "kind": "app_active",
        "entity_type": "app",
        "entity": "Code.exe",
        "payload": {"activity": "focus", "pid": 1234},
    }


def test_build_app_active_event_can_include_title_and_exe_path_when_enabled() -> None:
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    foreground = ForegroundApp(
        pid=1234,
        title="Project notes",
        exe_path=r"C:\Program Files\Code\Code.exe",
    )

    event = build_app_active_event(
        foreground,
        observed_at=observed_at,
        settings=ProbeSettings(store_titles=True, store_exe_path=True),
        seq=1,
    )

    assert event["title"] == "Project notes"
    assert event["payload"]["title"] == "Project notes"
    assert event["payload"]["exe_path"] == r"C:\Program Files\Code\Code.exe"


def test_probe_state_gates_idle_and_emits_on_change_or_heartbeat() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60, idle_cutoff_seconds=300))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    code = ForegroundApp(pid=10, title="Code", exe_path=r"C:\Code.exe")
    terminal = ForegroundApp(pid=11, title="Terminal", exe_path=r"C:\Terminal.exe")

    assert state.next_event(code, idle_seconds=0, observed_at=observed_at) is not None
    assert (
        state.next_event(
            code,
            idle_seconds=0,
            observed_at=observed_at + timedelta(seconds=30),
        )
        is None
    )
    assert (
        state.next_event(
            code,
            idle_seconds=0,
            observed_at=observed_at + timedelta(seconds=60),
        )
        is not None
    )
    assert (
        state.next_event(
            terminal,
            idle_seconds=0,
            observed_at=observed_at + timedelta(seconds=61),
        )
        is not None
    )
    assert (
        state.next_event(
            terminal,
            idle_seconds=300,
            observed_at=observed_at + timedelta(seconds=62),
        )
        is None
    )
    assert (
        state.next_event(
            terminal,
            idle_seconds=0,
            observed_at=observed_at + timedelta(seconds=63),
        )
        is not None
    )


def test_probe_settings_ignore_endpoint_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("LOCALTRACE_ENDPOINT", "http://10.0.0.5:8765/events")

    settings = _settings_from_args(_parse_args([]))

    assert settings.endpoint == "http://127.0.0.1:8765/events"


def test_probe_settings_allow_port_without_changing_loopback_host() -> None:
    settings = _settings_from_args(_parse_args(["--port", "9876"]))

    assert settings.endpoint == "http://127.0.0.1:9876/events"


def test_probe_cli_rejects_arbitrary_endpoint_argument() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--endpoint", "http://10.0.0.5:8765/events"])


def test_post_event_sends_json_to_configured_events_endpoint() -> None:
    received: list[tuple[str, str, dict[str, object]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                (
                    self.path,
                    self.headers["Content-Type"],
                    json.loads(body.decode("utf-8")),
                )
            )
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "id": 1}')

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        event = {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "payload": {"activity": "focus", "pid": 1234},
        }

        result = post_event(
            f"http://127.0.0.1:{server.server_port}/events",
            event,
            timeout_seconds=1,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.status == 201
    assert result.body == {"ok": True, "id": 1}
    assert received == [("/events", "application/json", event)]
