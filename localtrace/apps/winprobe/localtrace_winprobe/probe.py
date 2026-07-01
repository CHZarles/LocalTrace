from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

LOGGER = logging.getLogger("localtrace_winprobe")
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class ForegroundApp:
    pid: int
    title: str
    exe_path: str | None


@dataclass(frozen=True)
class ProbeSettings:
    api_port: int = DEFAULT_PORT
    poll_ms: int = 1000
    heartbeat_seconds: int = 60
    idle_cutoff_seconds: int = 300
    store_titles: bool = False
    store_exe_path: bool = False

    @property
    def endpoint(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.api_port}/events"


@dataclass(frozen=True)
class PostEventResult:
    status: int
    body: dict[str, Any]


class ActivityReader(Protocol):
    def idle_seconds(self) -> int: ...

    def foreground_app(self) -> ForegroundApp: ...


class ProbeState:
    def __init__(self, settings: ProbeSettings) -> None:
        self._settings = settings
        self._last_key: tuple[str, int, str] | None = None
        self._last_sent_at: datetime | None = None
        self._seq = 0

    def next_event(
        self,
        foreground: ForegroundApp | None,
        *,
        idle_seconds: int,
        observed_at: datetime,
    ) -> dict[str, Any] | None:
        if idle_seconds >= self._settings.idle_cutoff_seconds:
            self._last_key = None
            return None
        if foreground is None or foreground.pid == 0:
            return None

        key = self._key_for(foreground)
        due_heartbeat = (
            self._last_sent_at is None
            or (observed_at - self._last_sent_at).total_seconds()
            >= self._settings.heartbeat_seconds
        )
        if self._last_key == key and not due_heartbeat:
            return None

        return build_app_active_event(
            foreground,
            observed_at=observed_at,
            settings=self._settings,
            seq=self._seq + 1,
        )

    def mark_sent(self, foreground: ForegroundApp, *, observed_at: datetime) -> None:
        self._seq += 1
        self._last_key = self._key_for(foreground)
        self._last_sent_at = observed_at

    def _key_for(self, foreground: ForegroundApp) -> tuple[str, int, str]:
        title_key = foreground.title if self._settings.store_titles else ""
        return (_app_name(foreground), foreground.pid, title_key)


def build_app_active_event(
    foreground: ForegroundApp,
    *,
    observed_at: datetime,
    settings: ProbeSettings,
    seq: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "activity": "focus",
        "pid": foreground.pid,
    }
    event: dict[str, Any] = {
        "observed_at": _format_utc(observed_at),
        "source": "windows_probe",
        "kind": "app_active",
        "entity_type": "app",
        "entity": _app_name(foreground),
        "title": None,
        "payload": payload,
    }
    if seq is not None:
        event["seq"] = seq
    if settings.store_titles and foreground.title.strip():
        event["title"] = foreground.title
        payload["title"] = foreground.title
    if settings.store_exe_path and foreground.exe_path:
        payload["exe_path"] = foreground.exe_path
    return event


def post_event(
    endpoint: str,
    event: dict[str, Any],
    *,
    timeout_seconds: float = 5,
) -> PostEventResult:
    encoded = json.dumps(event, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return PostEventResult(
                status=int(response.status),
                body=_decode_json_response(response.read()),
            )
    except urllib.error.HTTPError as exc:
        return PostEventResult(
            status=int(exc.code),
            body=_decode_json_response(exc.read()),
        )


def run_probe(settings: ProbeSettings, reader: ActivityReader) -> None:
    LOGGER.info("localtrace-winprobe starting endpoint=%s", settings.endpoint)
    state = ProbeState(settings)
    while True:
        observed_at = datetime.now(UTC)
        idle_seconds = reader.idle_seconds()
        foreground = (
            None
            if idle_seconds >= settings.idle_cutoff_seconds
            else reader.foreground_app()
        )
        event = state.next_event(
            foreground,
            idle_seconds=idle_seconds,
            observed_at=observed_at,
        )
        if (
            event is not None
            and foreground is not None
            and _post_with_logging(settings, event)
        ):
            state.mark_sent(foreground, observed_at=observed_at)
        time.sleep(settings.poll_ms / 1000)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = _settings_from_args(_parse_args(argv))
    if sys.platform != "win32":
        LOGGER.error("localtrace-winprobe only captures foreground apps on Windows")
        return 1
    run_probe(settings, WindowsActivityReader())
    return 0


def _post_with_logging(settings: ProbeSettings, event: dict[str, Any]) -> bool:
    try:
        result = post_event(settings.endpoint, event)
    except OSError as exc:
        LOGGER.warning(
            "post failed kind=%s entity=%s error=%s",
            event["kind"],
            event["entity"],
            exc,
        )
        return False

    if 200 <= result.status < 300:
        LOGGER.info(
            "post success kind=%s entity=%s status=%s",
            event["kind"],
            event["entity"],
            result.status,
        )
        return True
    else:
        LOGGER.warning(
            "post failed kind=%s entity=%s status=%s body=%s",
            event["kind"],
            event["entity"],
            result.status,
            result.body,
        )
        return False


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="localtrace-winprobe")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="LocalTrace local API port.",
    )
    parser.add_argument("--poll-ms", type=int, default=1000)
    parser.add_argument("--heartbeat-seconds", type=int, default=60)
    parser.add_argument("--idle-cutoff-seconds", type=int, default=300)
    parser.add_argument("--store-titles", action="store_true")
    parser.add_argument("--store-exe-path", action="store_true")
    return parser.parse_args(argv)


def _settings_from_args(args: argparse.Namespace) -> ProbeSettings:
    return ProbeSettings(
        api_port=max(args.port, 1),
        poll_ms=max(args.poll_ms, 100),
        heartbeat_seconds=max(args.heartbeat_seconds, 1),
        idle_cutoff_seconds=max(args.idle_cutoff_seconds, 1),
        store_titles=args.store_titles,
        store_exe_path=args.store_exe_path,
    )


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _app_name(foreground: ForegroundApp) -> str:
    if foreground.exe_path:
        parts = [part for part in re.split(r"[\\/]+", foreground.exe_path) if part]
        if parts:
            return parts[-1]
    return f"pid:{foreground.pid}"


def _decode_json_response(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {"raw": raw.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


class WindowsActivityReader:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsActivityReader requires Windows")

    def idle_seconds(self) -> int:
        import ctypes
        from ctypes import wintypes

        class LastInputInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwTime", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        last_input = LastInputInfo()
        last_input.cbSize = ctypes.sizeof(LastInputInfo)
        if user32.GetLastInputInfo(ctypes.byref(last_input)) == 0:
            return 0
        now_ms = int(kernel32.GetTickCount64() & 0xFFFFFFFF)
        return int((now_ms - int(last_input.dwTime)) & 0xFFFFFFFF) // 1000

    def foreground_app(self) -> ForegroundApp:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ForegroundApp(pid=0, title="", exe_path=None)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        title_length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if title_length > 0:
            buffer = ctypes.create_unicode_buffer(title_length + 1)
            if user32.GetWindowTextW(hwnd, buffer, title_length + 1) > 0:
                title = buffer.value

        return ForegroundApp(
            pid=int(pid.value),
            title=title,
            exe_path=self._process_exe_path(int(pid.value)),
        )

    def _process_exe_path(self, pid: int) -> str | None:
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            ok = kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buffer,
                ctypes.byref(size),
            )
            if not ok or size.value == 0:
                return None
            return buffer.value
        finally:
            kernel32.CloseHandle(handle)
