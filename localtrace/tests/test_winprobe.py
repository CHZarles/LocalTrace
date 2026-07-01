import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from localtrace_winprobe.probe import (
    AudioApp,
    ForegroundApp,
    ProbeSettings,
    ProbeState,
    WindowsActivityReader,
    _parse_args,
    _settings_from_args,
    build_app_active_event,
    build_app_audio_event,
    build_app_audio_stop_event,
    is_browser_exe,
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
        "title": None,
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


def test_build_app_audio_event_uses_core_schema_and_privacy_defaults() -> None:
    observed_at = datetime(2026, 7, 1, 10, 31, tzinfo=UTC)
    audio = AudioApp(
        pid=5678,
        exe_path=r"C:\Program Files\Spotify\Spotify.exe",
    )

    event = build_app_audio_event(
        audio,
        observed_at=observed_at,
        settings=ProbeSettings(),
        seq=8,
    )

    assert event == {
        "observed_at": "2026-07-01T10:31:00.000Z",
        "source": "windows_probe",
        "seq": 8,
        "kind": "app_audio",
        "entity_type": "app",
        "entity": "Spotify.exe",
        "title": None,
        "payload": {"activity": "audio", "pid": 5678},
    }


def test_build_app_audio_event_can_include_exe_path_when_enabled() -> None:
    observed_at = datetime(2026, 7, 1, 10, 31, tzinfo=UTC)
    audio = AudioApp(
        pid=5678,
        exe_path=r"C:\Program Files\Spotify\Spotify.exe",
    )

    event = build_app_audio_event(
        audio,
        observed_at=observed_at,
        settings=ProbeSettings(store_exe_path=True),
        seq=8,
    )

    assert event["payload"]["exe_path"] == r"C:\Program Files\Spotify\Spotify.exe"


def test_build_app_audio_stop_event_includes_stop_reason() -> None:
    observed_at = datetime(2026, 7, 1, 10, 32, tzinfo=UTC)
    audio = AudioApp(
        pid=5678,
        exe_path=r"C:\Program Files\Spotify\Spotify.exe",
    )

    event = build_app_audio_stop_event(
        audio,
        observed_at=observed_at,
        settings=ProbeSettings(),
        seq=9,
    )

    assert event == {
        "observed_at": "2026-07-01T10:32:00.000Z",
        "source": "windows_probe",
        "seq": 9,
        "kind": "app_audio_stop",
        "entity_type": "app",
        "entity": "Spotify.exe",
        "title": None,
        "payload": {
            "activity": "audio",
            "pid": 5678,
            "reason": "no_active_audio_sessions",
        },
    }


def test_probe_state_gates_idle_and_emits_on_change_or_heartbeat() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60, idle_cutoff_seconds=300))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    code = ForegroundApp(pid=10, title="Code", exe_path=r"C:\Code.exe")
    terminal = ForegroundApp(pid=11, title="Terminal", exe_path=r"C:\Terminal.exe")

    assert state.next_event(code, idle_seconds=0, observed_at=observed_at) is not None
    state.mark_sent(code, observed_at=observed_at)
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
    state.mark_sent(code, observed_at=observed_at + timedelta(seconds=60))
    assert (
        state.next_event(
            terminal,
            idle_seconds=0,
            observed_at=observed_at + timedelta(seconds=61),
        )
        is not None
    )
    state.mark_sent(terminal, observed_at=observed_at + timedelta(seconds=61))
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


def test_probe_state_emits_audio_on_change_heartbeat_and_stop() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")
    music = AudioApp(pid=21, exe_path=r"C:\QQMusic.exe")

    first = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    assert first is not None
    assert first["kind"] == "app_audio"
    state.mark_audio_sent(spotify, observed_at=observed_at)

    assert (
        state.next_audio_event(
            spotify,
            poll_failed=False,
            observed_at=observed_at + timedelta(seconds=30),
        )
        is None
    )

    heartbeat = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=60),
    )
    assert heartbeat is not None
    assert heartbeat["kind"] == "app_audio"
    state.mark_audio_sent(spotify, observed_at=observed_at + timedelta(seconds=60))

    changed = state.next_audio_event(
        music,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=61),
    )
    assert changed is not None
    assert changed["kind"] == "app_audio"
    state.mark_audio_sent(music, observed_at=observed_at + timedelta(seconds=61))

    stopped = state.next_audio_event(
        None,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=62),
    )
    assert stopped is not None
    assert stopped["kind"] == "app_audio_stop"
    state.mark_audio_sent(None, observed_at=observed_at + timedelta(seconds=62))

    assert (
        state.next_audio_event(
            None,
            poll_failed=False,
            observed_at=observed_at + timedelta(seconds=63),
        )
        is None
    )


def test_probe_state_does_not_stop_audio_on_poll_error() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")

    first = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    assert first is not None
    state.mark_audio_sent(spotify, observed_at=observed_at)

    assert (
        state.next_audio_event(
            None,
            poll_failed=True,
            observed_at=observed_at + timedelta(seconds=1),
        )
        is None
    )

    stopped = state.next_audio_event(
        None,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=2),
    )

    assert stopped is not None
    assert stopped["kind"] == "app_audio_stop"


def test_probe_state_retries_audio_until_post_is_marked_sent() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")

    first = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    retry = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=1),
    )

    assert first is not None
    assert retry is not None
    assert first["seq"] == retry["seq"] == 1

    state.mark_audio_sent(spotify, observed_at=observed_at + timedelta(seconds=1))

    assert (
        state.next_audio_event(
            spotify,
            poll_failed=False,
            observed_at=observed_at + timedelta(seconds=2),
        )
        is None
    )


def test_browser_executables_are_excluded_from_app_audio() -> None:
    assert is_browser_exe("chrome.exe") is True
    assert is_browser_exe("msedge.exe") is True
    assert is_browser_exe("firefox.exe") is True
    assert is_browser_exe("spotify.exe") is False


def test_audio_candidates_treat_only_unknown_paths_as_poll_failure(
    monkeypatch,
    caplog,
) -> None:
    reader = object.__new__(WindowsActivityReader)
    paths = {
        10: None,
    }
    monkeypatch.setattr(reader, "_process_exe_path", lambda pid: paths[pid])
    caplog.set_level(logging.DEBUG, logger="localtrace_winprobe")

    with pytest.raises(OSError, match="executable path could not be resolved"):
        reader._audio_candidates([10])
    assert "executable path could not be resolved" in caplog.text


def test_audio_candidates_keep_known_apps_when_other_paths_are_unknown(
    monkeypatch,
    caplog,
) -> None:
    reader = object.__new__(WindowsActivityReader)
    paths = {
        10: r"C:\Program Files\Spotify\Spotify.exe",
        11: None,
    }
    monkeypatch.setattr(reader, "_process_exe_path", lambda pid: paths[pid])
    caplog.set_level(logging.DEBUG, logger="localtrace_winprobe")

    assert reader._audio_candidates([10, 11]) == [
        AudioApp(pid=10, exe_path=r"C:\Program Files\Spotify\Spotify.exe")
    ]
    assert "executable path could not be resolved" in caplog.text


def test_audio_candidates_exclude_browser_and_audiodg(monkeypatch) -> None:
    reader = object.__new__(WindowsActivityReader)
    paths = {
        10: r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        11: r"C:\Windows\System32\audiodg.exe",
        12: r"C:\Program Files\Spotify\Spotify.exe",
    }
    monkeypatch.setattr(reader, "_process_exe_path", lambda pid: paths[pid])

    assert reader._audio_candidates([10, 11, 12]) == [
        AudioApp(pid=12, exe_path=r"C:\Program Files\Spotify\Spotify.exe")
    ]


def test_audio_selection_emits_new_candidate_when_set_grows() -> None:
    reader = object.__new__(WindowsActivityReader)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")
    music = AudioApp(pid=21, exe_path=r"C:\QQMusic.exe")

    reader._last_audio_candidate_keys = reader._audio_candidate_keys([spotify])

    assert reader._select_audio_app([spotify, music], preferred_pid=20) == music


def test_audio_selection_keeps_preferred_candidate_when_set_is_stable() -> None:
    reader = object.__new__(WindowsActivityReader)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")
    music = AudioApp(pid=21, exe_path=r"C:\QQMusic.exe")
    reader._last_audio_candidate_keys = reader._audio_candidate_keys([spotify, music])

    assert reader._select_audio_app([spotify, music], preferred_pid=21) == music


def test_audio_retry_seq_stays_stable_across_foreground_posts() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")
    code = ForegroundApp(pid=10, title="Code", exe_path=r"C:\Code.exe")

    first_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    foreground = state.next_event(
        code,
        idle_seconds=0,
        observed_at=observed_at + timedelta(seconds=1),
    )
    assert foreground is not None
    assert foreground["seq"] == 2
    state.mark_sent(code, observed_at=observed_at + timedelta(seconds=1))
    retry_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=2),
    )

    assert first_audio is not None
    assert retry_audio is not None
    assert first_audio["seq"] == retry_audio["seq"] == 1


def test_failed_audio_stop_is_abandoned_when_same_app_resumes() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")

    first_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    assert first_audio is not None
    state.mark_audio_sent(spotify, observed_at=observed_at)
    failed_stop = state.next_audio_event(
        None,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=1),
    )
    resumed_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=2),
    )

    assert failed_stop is not None
    assert failed_stop["kind"] == "app_audio_stop"
    assert resumed_audio is not None
    assert resumed_audio["kind"] == "app_audio"
    assert resumed_audio["seq"] > failed_stop["seq"]


def test_failed_initial_audio_post_retries_even_if_app_disappears() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")

    first_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    retry_audio = state.next_audio_event(
        None,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=1),
    )

    assert first_audio is not None
    assert retry_audio is not None
    assert retry_audio["kind"] == "app_audio"
    assert retry_audio["entity"] == "Spotify.exe"
    assert retry_audio["seq"] == first_audio["seq"]


def test_pending_audio_retry_wins_over_new_active_app() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")
    music = AudioApp(pid=21, exe_path=r"C:\QQMusic.exe")

    first_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    retry_audio = state.next_audio_event(
        music,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=1),
    )

    assert first_audio is not None
    assert retry_audio is not None
    assert retry_audio["entity"] == "Spotify.exe"
    assert retry_audio["seq"] == first_audio["seq"]


def test_pending_audio_retry_marks_original_app_after_success() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    spotify = AudioApp(pid=20, exe_path=r"C:\Spotify.exe")

    first_audio = state.next_audio_event(
        spotify,
        poll_failed=False,
        observed_at=observed_at,
    )
    retry_audio = state.next_audio_event(
        None,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=1),
    )
    assert first_audio is not None
    assert retry_audio is not None

    state.mark_audio_event_sent(observed_at=observed_at + timedelta(seconds=1))
    stop_audio = state.next_audio_event(
        None,
        poll_failed=False,
        observed_at=observed_at + timedelta(seconds=2),
    )

    assert stop_audio is not None
    assert stop_audio["kind"] == "app_audio_stop"
    assert stop_audio["entity"] == "Spotify.exe"


def test_probe_state_retries_until_post_is_marked_sent() -> None:
    state = ProbeState(ProbeSettings(heartbeat_seconds=60, idle_cutoff_seconds=300))
    observed_at = datetime(2026, 7, 1, 10, 30, tzinfo=UTC)
    code = ForegroundApp(pid=10, title="Code", exe_path=r"C:\Code.exe")

    first = state.next_event(code, idle_seconds=0, observed_at=observed_at)
    retry = state.next_event(
        code,
        idle_seconds=0,
        observed_at=observed_at + timedelta(seconds=1),
    )

    assert first is not None
    assert retry is not None
    assert first["seq"] == retry["seq"] == 1

    state.mark_sent(code, observed_at=observed_at + timedelta(seconds=1))

    assert (
        state.next_event(
            code,
            idle_seconds=0,
            observed_at=observed_at + timedelta(seconds=2),
        )
        is None
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
