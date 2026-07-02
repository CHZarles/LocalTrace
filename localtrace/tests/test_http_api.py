import importlib
import json
import sqlite3
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from localtrace_core.app import LocalTraceService, create_http_server
from localtrace_core.config import default_config
from localtrace_core.storage import initialize_database


def make_service(tmp_path: Path) -> LocalTraceService:
    config = default_config(data_dir=tmp_path)
    initialize_database(config.db_path)
    return LocalTraceService(config)


def add_privacy_rule(
    service: LocalTraceService, entity_type: str, pattern: str, action: str
) -> None:
    with sqlite3.connect(service.config.db_path) as conn:
        conn.execute(
            """
            INSERT INTO privacy_rules (entity_type, pattern, action, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (entity_type, pattern, action, "2026-07-01T10:00:00.000Z"),
        )


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def request_text(base_url: str, path: str) -> tuple[int, str, str]:
    with urlopen(base_url + path, timeout=5) as response:
        content_type = response.headers.get("Content-Type", "")
        return response.status, content_type, response.read().decode("utf-8")


def test_web_dir_prefers_assets_next_to_runtime_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from localtrace_core import app as app_module

    runtime_web_dir = tmp_path / "web"
    runtime_web_dir.mkdir()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(sys, "executable", str(tmp_path / "localtrace.exe"))
            reloaded = importlib.reload(app_module)

            assert runtime_web_dir == reloaded.WEB_DIR
    finally:
        importlib.reload(app_module)


def test_health_reports_local_service_status(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    status, body = service.get_health()

    assert status == 200
    assert body["ok"] is True
    assert body["service"] == "localtrace"
    assert body["bind"]["host"] == "127.0.0.1"
    assert body["database"]["path"] == str(tmp_path / "localtrace.db")


def test_health_reports_event_count_and_source_recency(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "payload": {"activity": "focus"},
        }
    )
    service.post_events(
        {
            "observed_at": "2026-07-01T10:31:00.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "github.com",
            "payload": {"activity": "focus"},
        }
    )

    status, body = service.get_health()

    assert status == 200
    assert body["events"]["recent_count"] == 2
    assert body["sources"]["windows_probe"]["last_observed_at"] == (
        "2026-07-01T10:30:00.000Z"
    )
    assert body["sources"]["browser_extension"]["last_observed_at"] == (
        "2026-07-01T10:31:00.000Z"
    )


def test_http_server_binds_to_loopback_only(tmp_path: Path) -> None:
    config = default_config(data_dir=tmp_path)
    config.api.port = 0
    service = LocalTraceService(config)

    server = create_http_server(config, service)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_settings_api_returns_loopback_and_persists_approved_updates(
    tmp_path: Path,
) -> None:
    config = default_config(data_dir=tmp_path)
    initialize_database(config.db_path)
    config_path = tmp_path / "config.json"
    service = LocalTraceService(config, config_path=config_path)

    status, body = service.get_settings()

    assert status == 200
    assert body["settings"]["api"] == {"host": "127.0.0.1", "port": 8765}

    status, body = service.post_settings(
        {
            "api": {"port": 9876},
            "capture": {
                "poll_ms": 1500,
                "heartbeat_seconds": 90,
                "idle_cutoff_seconds": 420,
                "store_titles": True,
                "store_exe_path": True,
                "track_browser": False,
                "track_audio": False,
            },
        }
    )

    assert status == 200
    assert body["settings"]["api"] == {"host": "127.0.0.1", "port": 9876}
    assert body["settings"]["capture"]["poll_ms"] == 1500
    assert body["settings"]["capture"]["store_titles"] is True
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["api"]["port"] == 9876
    assert persisted["capture"]["heartbeat_seconds"] == 90


def test_settings_api_rejects_unknown_or_unsafe_values(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    invalid_payloads = [
        {"api": {"host": "0.0.0.0"}},
        {"api": {"port": 0}},
        {"capture": {"poll_ms": "fast"}},
        {"capture": {"unknown": True}},
        {"privacy": {"unknown": True}},
        {"unknown": {}},
    ]

    for payload in invalid_payloads:
        status, body = service.post_settings(payload)

        assert status == 400
        assert body["ok"] is False


def test_health_keeps_actual_bind_port_after_settings_port_update(
    tmp_path: Path,
) -> None:
    config = default_config(data_dir=tmp_path)
    config.api.port = 0
    initialize_database(config.db_path)
    service = LocalTraceService(config, config_path=tmp_path / "config.json")
    server = create_http_server(config, service)
    actual_port = server.server_address[1]
    try:
        status, body = service.post_settings({"api": {"port": 9876}})

        assert status == 200
        assert body["settings"]["api"]["port"] == 9876
        assert body["restart_required"] == ["api.port"]
        assert service.get_health()[1]["bind"]["port"] == actual_port
    finally:
        server.server_close()


def test_privacy_rule_api_validates_lists_creates_and_deletes_rules(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)

    status, body = service.get_privacy_rules()

    assert status == 200
    assert body == {"ok": True, "rules": []}

    status, body = service.post_privacy_rule(
        {"entity_type": "domain", "pattern": "github.com", "action": "mask"}
    )

    assert status == 201
    rule = body["rule"]
    assert rule["id"] == 1
    assert rule["entity_type"] == "domain"
    assert rule["pattern"] == "github.com"
    assert rule["action"] == "mask"

    status, body = service.get_privacy_rules()

    assert status == 200
    assert body["rules"] == [rule]

    status, body = service.post_privacy_rule(
        {"entity_type": "system", "pattern": "idle", "action": "drop"}
    )

    assert status == 400
    assert body["ok"] is False

    status, body = service.post_privacy_rule(
        {"entity_type": "domain", "pattern": "   ", "action": "mask"}
    )

    assert status == 400
    assert body["ok"] is False

    status, body = service.delete_privacy_rule(rule["id"])

    assert status == 200
    assert body == {"ok": True, "deleted": True}

    status, body = service.delete_privacy_rule(rule["id"])

    assert status == 404
    assert body == {"ok": False, "error": "privacy rule not found"}


def test_tracking_pause_prevents_event_storage_until_resumed(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    event = {
        "observed_at": "2026-07-01T10:30:00.000Z",
        "source": "windows_probe",
        "kind": "app_active",
        "entity_type": "app",
        "entity": "Code.exe",
        "payload": {"activity": "focus"},
    }

    status, body = service.get_tracking_status()

    assert status == 200
    assert body == {"ok": True, "paused": False}

    service.pause_tracking()
    status, body = service.post_events({"source": "windows_probe"})

    assert status == 400
    assert body["ok"] is False

    status, body = service.post_events(event)

    assert status == 202
    assert body == {"ok": True, "stored": False, "paused": True}
    assert service.get_events({})[1]["events"] == []

    service.resume_tracking()
    status, body = service.post_events(event)

    assert status == 201
    assert body["ok"] is True
    assert len(service.get_events({})[1]["events"]) == 1


def test_http_routes_expose_web_settings_and_local_json_apis(tmp_path: Path) -> None:
    config = default_config(data_dir=tmp_path)
    config.api.port = 0
    initialize_database(config.db_path)
    service = LocalTraceService(config, config_path=tmp_path / "config.json")
    server = create_http_server(config, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        status, content_type, html = request_text(base_url, "/")
        assert status == 200
        assert "text/html" in content_type
        assert "LocalTrace" in html
        assert "Today" in html
        assert "Now" in html
        assert "Today Top" in html
        assert "Timeline" in html
        assert "Recent flow" not in html
        assert "flowList" not in html
        assert "Recent events" not in html
        assert "eventsTable" not in html
        assert "settingsPanel" in html
        assert "/web/app.js" in html
        assert 'src="/web/app.js?v=' in html
        assert 'href="/web/styles.css?v=' in html
        assert "Dashboard" not in html
        assert "Reports" not in html
        assert "Planner" not in html
        assert "Review" not in html

        status, content_type, script = request_text(base_url, "/web/app.js")
        assert status == 200
        assert "javascript" in content_type
        assert "fetch" in script
        assert "/settings" in script
        assert "/privacy/rules" in script
        assert "/tracking/status" in script
        assert "/events?limit=500&order=desc" in script
        assert "renderToday" in script
        assert "buildTimelineModel" in script
        assert "avatar.append(badge)" not in script
        assert "restart required" in script

        status, content_type, styles = request_text(base_url, "/web/styles.css")
        assert status == 200
        assert "text/css" in content_type
        assert ":root" in styles
        assert ".nav-rail" in styles
        assert ".timeline-grid" in styles
        assert ".entity-avatar" in styles
        assert ".row-value > div" in styles
        assert ".timeline-lane-label > div" in styles
        assert ".row-value .entity-avatar" in styles
        assert ".timeline-lane-label .entity-avatar" in styles
        assert ".entity-icon" in styles
        assert "display: block;" in styles
        assert ".entity-avatar b" not in styles

        status, body = request_json(base_url, "/settings")
        assert status == 200
        assert body["settings"]["api"]["host"] == "127.0.0.1"

        status, body = request_json(
            base_url,
            "/privacy/rules",
            method="POST",
            payload={
                "entity_type": "domain",
                "pattern": "github.com",
                "action": "mask",
            },
        )
        assert status == 201
        rule_id = body["rule"]["id"]

        status, body = request_json(
            base_url, f"/privacy/rules/{rule_id}", method="DELETE"
        )
        assert status == 200
        assert body == {"ok": True, "deleted": True}

        status, body = request_json(base_url, "/tracking/pause", method="POST")
        assert status == 200
        assert body == {"ok": True, "paused": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_post_events_validates_and_stores_raw_events(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    status, body = service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "windows_probe",
            "seq": 123,
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": "Sensitive project title",
            "payload": {
                "pid": 1234,
                "activity": "focus",
                "title": "Nested sensitive title",
                "exe_path": "C:/Users/charles/AppData/Local/Programs/Code.exe",
            },
        }
    )

    assert status == 201
    assert body["ok"] is True
    assert body["id"] == 1

    status, query = service.get_events({"source": "windows_probe"})

    assert status == 200
    assert len(query["events"]) == 1
    event = query["events"][0]
    assert event["observed_at"] == "2026-07-01T10:30:00.000Z"
    assert event["source"] == "windows_probe"
    assert event["kind"] == "app_active"
    assert event["entity_type"] == "app"
    assert event["entity"] == "Code.exe"
    assert event["title"] is None
    assert event["payload"] == {"pid": 1234, "activity": "focus"}
    assert event["received_at"].endswith("Z")


def test_post_events_keeps_titles_and_exe_path_when_configured(tmp_path: Path) -> None:
    config = default_config(data_dir=tmp_path)
    config.capture.store_titles = True
    config.capture.store_exe_path = True
    initialize_database(config.db_path)
    service = LocalTraceService(config)

    service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": "Project notes",
            "payload": {
                "pid": 1234,
                "activity": "focus",
                "title": "Nested project title",
                "exe_path": "C:/Program Files/Code/Code.exe",
            },
        }
    )

    event = service.get_events({})[1]["events"][0]
    assert event["title"] == "Project notes"
    assert event["payload"]["title"] == "Nested project title"
    assert event["payload"]["exe_path"] == "C:/Program Files/Code/Code.exe"


def test_post_events_rejects_disallowed_event_kind(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    status, body = service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "windows_probe",
            "kind": "idle_start",
            "entity_type": "system",
            "entity": "idle",
            "payload": {},
        }
    )

    assert status == 400
    assert body["ok"] is False
    assert "kind" in body["error"]
    assert service.get_events({})[1]["events"] == []


def test_post_events_rejects_invalid_source_kind_entity_type_combinations(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)

    invalid_events = [
        {
            "source": "browser_extension",
            "kind": "app_audio",
            "entity_type": "domain",
            "entity": "github.com",
        },
        {
            "source": "windows_probe",
            "kind": "tab_active",
            "entity_type": "app",
            "entity": "Code.exe",
        },
        {
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "domain",
            "entity": "code.example",
        },
    ]

    for index, event in enumerate(invalid_events):
        status, body = service.post_events(
            {
                "observed_at": f"2026-07-01T10:30:0{index}.000Z",
                "payload": {},
                **event,
            }
        )

        assert status == 400
        assert body["ok"] is False
        assert "combination" in body["error"]

    assert service.get_events({})[1]["events"] == []


def test_post_events_rejects_non_utc_observed_at(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    status, body = service.post_events(
        {
            "observed_at": "2026-07-01T18:30:00.000+08:00",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "payload": {},
        }
    )

    assert status == 400
    assert body["ok"] is False
    assert "UTC" in body["error"]
    assert service.get_events({})[1]["events"] == []


def test_post_events_normalizes_utc_offset_observed_at(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    status, _body = service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00+00:00",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "payload": {},
        }
    )

    assert status == 201
    assert service.get_events({})[1]["events"][0]["observed_at"] == (
        "2026-07-01T10:30:00.000Z"
    )


def test_post_events_applies_drop_privacy_rule_to_domain_subdomains(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    add_privacy_rule(service, "domain", "github.com", "drop")

    status, body = service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "private.github.com",
            "title": "Sensitive repository",
            "payload": {"activity": "focus"},
        }
    )

    assert status == 202
    assert body == {"ok": True, "stored": False}
    assert service.get_events({})[1]["events"] == []


def test_post_events_applies_mask_privacy_rule(tmp_path: Path) -> None:
    config = default_config(data_dir=tmp_path)
    config.capture.store_titles = True
    config.capture.store_exe_path = True
    initialize_database(config.db_path)
    service = LocalTraceService(config)
    add_privacy_rule(service, "app", "Code.exe", "mask")

    status, _body = service.post_events(
        {
            "observed_at": "2026-07-01T10:30:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": "Sensitive project title",
            "payload": {
                "activity": "focus",
                "exe_path": "C:/Users/charles/AppData/Local/Programs/Code.exe",
            },
        }
    )

    assert status == 201
    event = service.get_events({})[1]["events"][0]
    assert event["entity"] == "__hidden__"
    assert event["title"] is None
    assert event["payload"] == {"activity": "focus"}


def test_get_events_filters_by_time_source_kind_and_limit(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.post_events(
        {
            "observed_at": "2026-07-01T09:00:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "payload": {"pid": 1},
        }
    )
    service.post_events(
        {
            "observed_at": "2026-07-01T10:00:00.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "github.com",
            "payload": {"activity": "focus"},
        }
    )
    service.post_events(
        {
            "observed_at": "2026-07-01T11:00:00.000Z",
            "source": "browser_extension",
            "kind": "tab_audio_stop",
            "entity_type": "domain",
            "entity": "youtube.com",
            "payload": {"activity": "audio"},
        }
    )

    status, body = service.get_events(
        {
            "from": "2026-07-01T09:30:00.000Z",
            "to": "2026-07-01T12:00:00.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "limit": "1",
        }
    )

    assert status == 200
    assert [event["entity"] for event in body["events"]] == ["github.com"]


def test_get_events_supports_explicit_desc_order_for_recent_views(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    for index, entity in enumerate(["Code.exe", "chrome.exe", "WindowsTerminal.exe"]):
        service.post_events(
            {
                "observed_at": f"2026-07-01T10:0{index}:00.000Z",
                "source": "windows_probe",
                "kind": "app_active",
                "entity_type": "app",
                "entity": entity,
                "payload": {"activity": "focus"},
            }
        )

    status, body = service.get_events({"limit": "2", "order": "desc"})

    assert status == 200
    assert [event["entity"] for event in body["events"]] == [
        "WindowsTerminal.exe",
        "chrome.exe",
    ]


def test_get_events_excludes_to_boundary(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.post_events(
        {
            "observed_at": "2026-07-01T10:00:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "before.exe",
            "payload": {},
        }
    )
    service.post_events(
        {
            "observed_at": "2026-07-01T11:00:00.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "boundary.exe",
            "payload": {},
        }
    )

    status, body = service.get_events({"to": "2026-07-01T11:00:00.000Z"})

    assert status == 200
    assert [event["entity"] for event in body["events"]] == ["before.exe"]


def test_get_events_defaults_to_limit_200(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    for index in range(201):
        service.post_events(
            {
                "observed_at": f"2026-07-01T10:{index // 60:02}:{index % 60:02}.000Z",
                "source": "windows_probe",
                "kind": "app_active",
                "entity_type": "app",
                "entity": f"app-{index}.exe",
                "payload": {},
            }
        )

    status, body = service.get_events({})

    assert status == 200
    assert len(body["events"]) == 200
    assert body["events"][-1]["entity"] == "app-199.exe"
