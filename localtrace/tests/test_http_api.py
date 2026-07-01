import sqlite3
from pathlib import Path

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


def test_health_reports_local_service_status(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    status, body = service.get_health()

    assert status == 200
    assert body["ok"] is True
    assert body["service"] == "localtrace"
    assert body["bind"]["host"] == "127.0.0.1"
    assert body["database"]["path"] == str(tmp_path / "localtrace.db")


def test_http_server_binds_to_loopback_only(tmp_path: Path) -> None:
    config = default_config(data_dir=tmp_path)
    config.api.port = 0
    service = LocalTraceService(config)

    server = create_http_server(config, service)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


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
                "exe_path": "C:/Program Files/Code/Code.exe",
            },
        }
    )

    event = service.get_events({})[1]["events"][0]
    assert event["title"] == "Project notes"
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
