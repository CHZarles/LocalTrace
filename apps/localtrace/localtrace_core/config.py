from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

LOOPBACK_HOST = "127.0.0.1"


@dataclass
class ApiConfig:
    port: int = 8765

    @property
    def host(self) -> str:
        return LOOPBACK_HOST


@dataclass
class CaptureConfig:
    poll_ms: int = 1000
    heartbeat_seconds: int = 60
    idle_cutoff_seconds: int = 300
    store_titles: bool = True
    store_exe_path: bool = True
    track_browser: bool = True
    track_audio: bool = True


@dataclass
class PrivacyConfig:
    pass


@dataclass
class LocalTraceConfig:
    data_dir: Path
    api: ApiConfig
    capture: CaptureConfig
    privacy: PrivacyConfig

    @property
    def db_path(self) -> Path:
        return self.data_dir / "localtrace.db"


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "LocalTrace"
    return Path.home() / ".local" / "share" / "LocalTrace"


def default_config(data_dir: Path | None = None) -> LocalTraceConfig:
    return LocalTraceConfig(
        data_dir=data_dir or default_data_dir(),
        api=ApiConfig(),
        capture=CaptureConfig(),
        privacy=PrivacyConfig(),
    )


def load_config(path: Path, data_dir: Path | None = None) -> LocalTraceConfig:
    config = default_config(data_dir=data_dir)
    if not path.exists():
        return config

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid LocalTrace config JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("Invalid LocalTrace config JSON")

    api = _section(raw, "api")
    capture = _section(raw, "capture")
    config.api.port = _bounded_int(api, "port", config.api.port, 1, 65535)
    config.capture.poll_ms = _int(capture, "poll_ms", config.capture.poll_ms)
    config.capture.heartbeat_seconds = _int(
        capture, "heartbeat_seconds", config.capture.heartbeat_seconds
    )
    config.capture.idle_cutoff_seconds = _int(
        capture, "idle_cutoff_seconds", config.capture.idle_cutoff_seconds
    )
    config.capture.store_titles = _bool(
        capture, "store_titles", config.capture.store_titles
    )
    config.capture.store_exe_path = _bool(
        capture, "store_exe_path", config.capture.store_exe_path
    )
    config.capture.track_browser = _bool(
        capture, "track_browser", config.capture.track_browser
    )
    config.capture.track_audio = _bool(
        capture, "track_audio", config.capture.track_audio
    )
    return config


def load_or_create_config(path: Path, data_dir: Path | None = None) -> LocalTraceConfig:
    exists = path.exists()
    config = load_config(path, data_dir=data_dir)
    if not exists:
        save_config(config, path)
    return config


def save_config(config: LocalTraceConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "api": {"port": config.api.port},
        "capture": asdict(config.capture),
        "privacy": asdict(config.privacy),
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    return value if isinstance(value, dict) else {}


def _int(raw: dict[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _bounded_int(
    raw: dict[str, Any], key: str, default: int, minimum: int, maximum: int
) -> int:
    value = _int(raw, key, default)
    return value if minimum <= value <= maximum else default


def _bool(raw: dict[str, Any], key: str, default: bool) -> bool:
    value = raw.get(key, default)
    return value if isinstance(value, bool) else default
