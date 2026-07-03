import json
from dataclasses import asdict
from pathlib import Path

import pytest

from localtrace_core.config import (
    default_config,
    load_config,
    load_or_create_config,
    save_config,
)


def test_missing_config_uses_local_only_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"

    config = load_config(config_path, data_dir=tmp_path)

    assert config.api.host == "127.0.0.1"
    assert config.api.port == 8765
    assert config.capture.poll_ms == 1000
    assert config.capture.heartbeat_seconds == 60
    assert config.capture.idle_cutoff_seconds == 300
    assert config.capture.store_titles is True
    assert config.capture.store_exe_path is True
    assert config.capture.track_browser is True
    assert config.capture.track_audio is True
    assert config.data_dir == tmp_path
    assert config.db_path == tmp_path / "localtrace.db"


def test_config_can_be_saved_and_loaded(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config = default_config(data_dir=tmp_path)
    config.api.port = 9999
    config.capture.store_titles = False
    config.capture.store_exe_path = False

    save_config(config, config_path)
    loaded = load_config(config_path, data_dir=tmp_path)

    assert loaded.api.host == "127.0.0.1"
    assert loaded.api.port == 9999
    assert loaded.capture.store_titles is False
    assert loaded.capture.store_exe_path is False
    assert "host" not in config_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_stored_api_port_falls_back_to_default(
    tmp_path: Path, port: int
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"api": {"port": port}}), encoding="utf-8")

    config = load_config(config_path, data_dir=tmp_path)

    assert config.api.port == 8765


def test_missing_config_is_saved_with_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"

    config = load_or_create_config(config_path, data_dir=tmp_path)

    assert config_path.exists()
    assert config.data_dir == tmp_path
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["api"]["port"] == 8765
    assert saved["capture"]["store_titles"] is True
    assert saved["capture"]["store_exe_path"] is True
    assert saved["privacy"] == {}
    assert "host" not in saved["api"]


def test_legacy_default_title_storage_key_is_ignored(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"privacy": {"default_title_storage": True}}),
        encoding="utf-8",
    )

    config = load_config(config_path, data_dir=tmp_path)

    assert "default_title_storage" not in asdict(config.privacy)


def test_invalid_config_json_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid LocalTrace config JSON"):
        load_config(config_path, data_dir=tmp_path)
