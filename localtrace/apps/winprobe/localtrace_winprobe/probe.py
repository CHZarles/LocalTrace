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
class AudioApp:
    pid: int
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

    def active_audio_app(self, preferred_pid: int | None) -> AudioApp | None: ...


class ProbeState:
    def __init__(self, settings: ProbeSettings) -> None:
        self._settings = settings
        self._last_foreground_key: tuple[str, int, str] | None = None
        self._last_foreground_sent_at: datetime | None = None
        self._last_audio: AudioApp | None = None
        self._last_audio_sent_at: datetime | None = None
        self._seq = 0
        self._pending_foreground_key: tuple[str, int, str] | None = None
        self._pending_foreground_seq: int | None = None
        self._pending_audio_key: tuple[str, tuple[str, int] | None] | None = None
        self._pending_audio_seq: int | None = None

    @property
    def preferred_audio_pid(self) -> int | None:
        return self._last_audio.pid if self._last_audio is not None else None

    def next_event(
        self,
        foreground: ForegroundApp | None,
        *,
        idle_seconds: int,
        observed_at: datetime,
    ) -> dict[str, Any] | None:
        if idle_seconds >= self._settings.idle_cutoff_seconds:
            self._last_foreground_key = None
            self._clear_pending_foreground()
            return None
        if foreground is None or foreground.pid == 0:
            self._clear_pending_foreground()
            return None

        key = self._key_for(foreground)
        due_heartbeat = (
            self._last_foreground_sent_at is None
            or (observed_at - self._last_foreground_sent_at).total_seconds()
            >= self._settings.heartbeat_seconds
        )
        if self._last_foreground_key == key and not due_heartbeat:
            return None

        seq = self._seq_for_foreground(key)
        return build_app_active_event(
            foreground,
            observed_at=observed_at,
            settings=self._settings,
            seq=seq,
        )

    def mark_sent(self, foreground: ForegroundApp, *, observed_at: datetime) -> None:
        self._clear_pending_foreground()
        self._last_foreground_key = self._key_for(foreground)
        self._last_foreground_sent_at = observed_at

    def next_audio_event(
        self,
        audio: AudioApp | None,
        *,
        poll_failed: bool,
        observed_at: datetime,
    ) -> dict[str, Any] | None:
        if poll_failed:
            return None

        if audio is None:
            if self._last_audio is None:
                self._clear_pending_audio()
                return None
            pending_key: tuple[str, tuple[str, int] | None] = (
                "stop",
                self._audio_key_for(self._last_audio),
            )
            seq = self._seq_for_audio(pending_key)
            return build_app_audio_stop_event(
                self._last_audio,
                observed_at=observed_at,
                settings=self._settings,
                seq=seq,
            )

        key = self._audio_key_for(audio)
        last_key = (
            None if self._last_audio is None else self._audio_key_for(self._last_audio)
        )
        due_heartbeat = (
            self._last_audio_sent_at is None
            or (observed_at - self._last_audio_sent_at).total_seconds()
            >= self._settings.heartbeat_seconds
        )
        if last_key == key and not due_heartbeat:
            return None

        seq = self._seq_for_audio(("audio", key))
        return build_app_audio_event(
            audio,
            observed_at=observed_at,
            settings=self._settings,
            seq=seq,
        )

    def mark_audio_sent(
        self,
        audio: AudioApp | None,
        *,
        observed_at: datetime,
    ) -> None:
        self._clear_pending_audio()
        self._last_audio = audio
        self._last_audio_sent_at = observed_at

    def _key_for(self, foreground: ForegroundApp) -> tuple[str, int, str]:
        title_key = foreground.title if self._settings.store_titles else ""
        return (_app_name(foreground), foreground.pid, title_key)

    def _audio_key_for(self, audio: AudioApp) -> tuple[str, int]:
        return (_audio_app_name(audio), audio.pid)

    def _seq_for_foreground(self, key: tuple[str, int, str]) -> int:
        if (
            self._pending_foreground_key == key
            and self._pending_foreground_seq is not None
        ):
            return self._pending_foreground_seq
        seq = self._reserve_seq()
        self._pending_foreground_key = key
        self._pending_foreground_seq = seq
        return seq

    def _seq_for_audio(self, key: tuple[str, tuple[str, int] | None]) -> int:
        if self._pending_audio_key == key and self._pending_audio_seq is not None:
            return self._pending_audio_seq
        seq = self._reserve_seq()
        self._pending_audio_key = key
        self._pending_audio_seq = seq
        return seq

    def _reserve_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _clear_pending_foreground(self) -> None:
        self._pending_foreground_key = None
        self._pending_foreground_seq = None

    def _clear_pending_audio(self) -> None:
        self._pending_audio_key = None
        self._pending_audio_seq = None


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


def build_app_audio_event(
    audio: AudioApp,
    *,
    observed_at: datetime,
    settings: ProbeSettings,
    seq: int | None = None,
) -> dict[str, Any]:
    payload = _audio_payload(audio, settings)
    event: dict[str, Any] = {
        "observed_at": _format_utc(observed_at),
        "source": "windows_probe",
        "kind": "app_audio",
        "entity_type": "app",
        "entity": _audio_app_name(audio),
        "title": None,
        "payload": payload,
    }
    if seq is not None:
        event["seq"] = seq
    return event


def build_app_audio_stop_event(
    audio: AudioApp,
    *,
    observed_at: datetime,
    settings: ProbeSettings,
    seq: int | None = None,
) -> dict[str, Any]:
    payload = _audio_payload(audio, settings)
    payload["reason"] = "no_active_audio_sessions"
    event: dict[str, Any] = {
        "observed_at": _format_utc(observed_at),
        "source": "windows_probe",
        "kind": "app_audio_stop",
        "entity_type": "app",
        "entity": _audio_app_name(audio),
        "title": None,
        "payload": payload,
    }
    if seq is not None:
        event["seq"] = seq
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

        audio_poll_failed = False
        audio: AudioApp | None = None
        try:
            audio = reader.active_audio_app(state.preferred_audio_pid)
        except OSError as exc:
            LOGGER.warning("audio poll failed error=%s", exc)
            audio_poll_failed = True

        audio_event = state.next_audio_event(
            audio,
            poll_failed=audio_poll_failed,
            observed_at=observed_at,
        )
        if audio_event is not None and _post_with_logging(settings, audio_event):
            state.mark_audio_sent(audio, observed_at=observed_at)
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
    return _process_name(foreground.pid, foreground.exe_path)


def _audio_app_name(audio: AudioApp) -> str:
    return _process_name(audio.pid, audio.exe_path)


def _process_name(pid: int, exe_path: str | None) -> str:
    if exe_path:
        parts = [part for part in re.split(r"[\\/]+", exe_path) if part]
        if parts:
            return parts[-1]
    return f"pid:{pid}"


def _audio_payload(audio: AudioApp, settings: ProbeSettings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "activity": "audio",
        "pid": audio.pid,
    }
    if settings.store_exe_path and audio.exe_path:
        payload["exe_path"] = audio.exe_path
    return payload


def is_browser_exe(exe_name: str) -> bool:
    return exe_name.lower() in {
        "chrome.exe",
        "msedge.exe",
        "brave.exe",
        "vivaldi.exe",
        "opera.exe",
        "firefox.exe",
    }


def _is_excluded_audio_exe(exe_name: str) -> bool:
    lowered = exe_name.lower()
    return lowered == "audiodg.exe" or is_browser_exe(lowered)


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
        self._last_audio_candidate_keys: tuple[tuple[str, int], ...] | None = None

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

    def active_audio_app(self, preferred_pid: int | None) -> AudioApp | None:
        import ctypes
        from ctypes import wintypes

        hresult = ctypes.c_long
        clsctx_all = 0x17
        coinit_multithreaded = 0x0
        s_ok = 0
        s_false = 1
        rpc_e_changed_mode = -2147417850
        e_render = 0
        e_multimedia = 1
        audio_session_state_active = 1

        class GUID(ctypes.Structure):
            _fields_ = [
                ("data1", wintypes.DWORD),
                ("data2", wintypes.WORD),
                ("data3", wintypes.WORD),
                ("data4", ctypes.c_ubyte * 8),
            ]

        def guid(
            data1: int,
            data2: int,
            data3: int,
            data4: tuple[int, int, int, int, int, int, int, int],
        ) -> GUID:
            return GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4))

        clsid_mm_device_enumerator = guid(
            0xBCDE0395,
            0xE52F,
            0x467C,
            (0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E),
        )
        iid_mm_device_enumerator = guid(
            0xA95664D2,
            0x9614,
            0x4F35,
            (0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6),
        )
        iid_audio_session_manager2 = guid(
            0x77AA99A0,
            0x1BD6,
            0x484F,
            (0x8B, 0xC7, 0x2C, 0x65, 0x4C, 0x9A, 0x9B, 0x6F),
        )
        iid_audio_session_control2 = guid(
            0xBFB7FF88,
            0x7239,
            0x4FC9,
            (0x8F, 0xA2, 0x07, 0xC9, 0x50, 0xBE, 0x9C, 0x6D),
        )

        def failed(value: int) -> bool:
            return ctypes.c_long(value).value < 0

        def check(value: int, action: str) -> None:
            if failed(value):
                raise OSError(
                    f"{action} failed with HRESULT 0x{value & 0xFFFFFFFF:08X}"
                )

        def com_method(
            pointer: ctypes.c_void_p,
            index: int,
            restype: type[ctypes._SimpleCData],
            *argtypes: object,
        ) -> object:
            vtable = ctypes.cast(
                pointer,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
            ).contents
            prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
            return prototype(vtable[index])

        def release(pointer: ctypes.c_void_p | None) -> None:
            if pointer:
                method = com_method(pointer, 2, wintypes.ULONG)
                method(pointer)

        ole32 = ctypes.windll.ole32
        initialized = False
        enumerator = ctypes.c_void_p()
        device = ctypes.c_void_p()
        manager = ctypes.c_void_p()
        sessions = ctypes.c_void_p()
        controls: list[ctypes.c_void_p] = []
        control2s: list[ctypes.c_void_p] = []
        try:
            hr = int(ole32.CoInitializeEx(None, coinit_multithreaded))
            if hr in {s_ok, s_false}:
                initialized = True
            elif hr != rpc_e_changed_mode:
                check(hr, "CoInitializeEx")

            hr = int(
                ole32.CoCreateInstance(
                    ctypes.byref(clsid_mm_device_enumerator),
                    None,
                    clsctx_all,
                    ctypes.byref(iid_mm_device_enumerator),
                    ctypes.byref(enumerator),
                )
            )
            check(hr, "CoCreateInstance")

            get_default_audio_endpoint = com_method(
                enumerator,
                4,
                hresult,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            )
            check(
                int(
                    get_default_audio_endpoint(
                        enumerator,
                        e_render,
                        e_multimedia,
                        ctypes.byref(device),
                    )
                ),
                "GetDefaultAudioEndpoint",
            )

            activate = com_method(
                device,
                3,
                hresult,
                ctypes.POINTER(GUID),
                wintypes.DWORD,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            )
            check(
                int(
                    activate(
                        device,
                        ctypes.byref(iid_audio_session_manager2),
                        clsctx_all,
                        None,
                        ctypes.byref(manager),
                    )
                ),
                "IMMDevice.Activate",
            )

            get_session_enumerator = com_method(
                manager,
                5,
                hresult,
                ctypes.POINTER(ctypes.c_void_p),
            )
            check(
                int(get_session_enumerator(manager, ctypes.byref(sessions))),
                "GetSessionEnumerator",
            )

            get_count = com_method(
                sessions,
                3,
                hresult,
                ctypes.POINTER(ctypes.c_int),
            )
            count = ctypes.c_int()
            check(int(get_count(sessions, ctypes.byref(count))), "GetCount")

            active_pids: list[int] = []
            get_session = com_method(
                sessions,
                4,
                hresult,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            )
            for index in range(count.value):
                control = ctypes.c_void_p()
                check(
                    int(get_session(sessions, index, ctypes.byref(control))),
                    "GetSession",
                )
                controls.append(control)

                get_state = com_method(
                    control,
                    3,
                    hresult,
                    ctypes.POINTER(ctypes.c_int),
                )
                state = ctypes.c_int()
                check(int(get_state(control, ctypes.byref(state))), "GetState")
                if state.value != audio_session_state_active:
                    continue

                query_interface = com_method(
                    control,
                    0,
                    hresult,
                    ctypes.POINTER(GUID),
                    ctypes.POINTER(ctypes.c_void_p),
                )
                control2 = ctypes.c_void_p()
                hr = int(
                    query_interface(
                        control,
                        ctypes.byref(iid_audio_session_control2),
                        ctypes.byref(control2),
                    )
                )
                if failed(hr):
                    continue
                control2s.append(control2)

                get_process_id = com_method(
                    control2,
                    14,
                    hresult,
                    ctypes.POINTER(wintypes.DWORD),
                )
                pid = wintypes.DWORD()
                check(
                    int(get_process_id(control2, ctypes.byref(pid))),
                    "GetProcessId",
                )
                if pid.value:
                    active_pids.append(int(pid.value))

            candidates = self._audio_candidates(sorted(set(active_pids)))
            selected = self._select_audio_app(candidates, preferred_pid)
            self._last_audio_candidate_keys = self._audio_candidate_keys(candidates)
            return selected
        finally:
            for pointer in control2s:
                release(pointer)
            for pointer in controls:
                release(pointer)
            release(sessions)
            release(manager)
            release(device)
            release(enumerator)
            if initialized:
                ole32.CoUninitialize()

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

    def _audio_candidates(self, pids: list[int]) -> list[AudioApp]:
        candidates: list[AudioApp] = []
        unresolved_path = False
        for pid in pids:
            exe_path = self._process_exe_path(pid)
            if exe_path is None:
                LOGGER.debug(
                    "skipping audio pid=%s because executable path could not be "
                    "resolved",
                    pid,
                )
                unresolved_path = True
                continue
            app_name = _process_name(pid, exe_path)
            if _is_excluded_audio_exe(app_name):
                continue
            candidates.append(AudioApp(pid=pid, exe_path=exe_path))
        if unresolved_path and not candidates:
            raise OSError("audio executable path could not be resolved")
        return candidates

    def _select_audio_app(
        self,
        candidates: list[AudioApp],
        preferred_pid: int | None,
    ) -> AudioApp | None:
        if not candidates:
            return None

        if preferred_pid is not None:
            for candidate in candidates:
                if candidate.pid == preferred_pid:
                    return candidate

        candidate_keys = self._audio_candidate_keys(candidates)
        previous_keys = self._last_audio_candidate_keys
        if previous_keys is not None and previous_keys != candidate_keys:
            previous_key_set = set(previous_keys)
            for candidate in candidates:
                if self._audio_candidate_key(candidate) not in previous_key_set:
                    return candidate

        return min(candidates, key=lambda candidate: candidate.pid)

    def _audio_candidate_keys(
        self,
        candidates: list[AudioApp],
    ) -> tuple[tuple[str, int], ...]:
        return tuple(
            sorted(self._audio_candidate_key(candidate) for candidate in candidates)
        )

    def _audio_candidate_key(self, candidate: AudioApp) -> tuple[str, int]:
        return (_audio_app_name(candidate), candidate.pid)
