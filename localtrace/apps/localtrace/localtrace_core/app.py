from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import (
    LOOPBACK_HOST,
    LocalTraceConfig,
    default_config,
    load_or_create_config,
    save_config,
)
from .storage import (
    count_recent_events,
    delete_privacy_rule,
    initialize_database,
    insert_event,
    insert_privacy_rule,
    latest_events_by_source,
    list_all_privacy_rules,
    list_events,
    list_privacy_rules,
)

ALLOWED_SOURCES = {"windows_probe", "browser_extension"}
ALLOWED_KINDS = {
    "app_active",
    "app_audio",
    "app_audio_stop",
    "tab_active",
    "tab_audio_stop",
}
ALLOWED_ENTITY_TYPES = {"app", "domain", "system"}
EVENT_CONTRACTS = {
    "app_active": ("windows_probe", "app"),
    "app_audio": ("windows_probe", "app"),
    "app_audio_stop": ("windows_probe", "app"),
    "tab_active": ("browser_extension", "domain"),
    "tab_audio_stop": ("browser_extension", "domain"),
}
EXE_PATH_FIELDS = {"exe_path", "exePath"}
ALWAYS_FILTERED_PAYLOAD_FIELDS = {"url", "full_url", "path"}
TITLE_PAYLOAD_FIELDS = {"title", "window_title", "tab_title"}
MASKED_PAYLOAD_FIELDS = (
    ALWAYS_FILTERED_PAYLOAD_FIELDS | EXE_PATH_FIELDS | TITLE_PAYLOAD_FIELDS
)
WEB_DIR = Path(__file__).resolve().parents[3] / "web"
STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class LocalTraceService:
    def __init__(
        self, config: LocalTraceConfig, config_path: Path | None = None
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.tracking_paused = False
        self.bind_host = LOOPBACK_HOST
        self.bind_port = config.api.port

    def get_health(self) -> tuple[int, dict[str, Any]]:
        recent_since = _format_rfc3339_utc(datetime.now(UTC) - timedelta(days=1))
        sources = {
            source: {"last_observed_at": None, "last_received_at": None}
            for source in sorted(ALLOWED_SOURCES)
        }
        sources.update(latest_events_by_source(self.config.db_path))
        return 200, {
            "ok": True,
            "service": "localtrace",
            "bind": {
                "host": self.bind_host,
                "port": self.bind_port,
            },
            "database": {
                "path": str(self.config.db_path),
                "exists": self.config.db_path.exists(),
            },
            "data_dir": str(self.config.data_dir),
            "events": {
                "recent_count": count_recent_events(self.config.db_path, recent_since)
            },
            "sources": sources,
            "tracking": {"paused": self.tracking_paused},
        }

    def post_events(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.tracking_paused:
            return 202, {"ok": True, "stored": False, "paused": True}

        try:
            event = self._normalize_event(payload)
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

        event = self._apply_privacy_rules(event)
        if event is None:
            return 202, {"ok": True, "stored": False}

        event_id = insert_event(self.config.db_path, event)
        return 201, {"ok": True, "id": event_id}

    def get_events(self, filters: dict[str, str]) -> tuple[int, dict[str, Any]]:
        return 200, {"ok": True, "events": list_events(self.config.db_path, filters)}

    def get_settings(self) -> tuple[int, dict[str, Any]]:
        return 200, {"ok": True, "settings": _settings_payload(self.config)}

    def post_settings(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            updates = _validate_settings_payload(payload)
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

        api = updates.get("api", {})
        capture = updates.get("capture", {})
        privacy = updates.get("privacy", {})

        if "port" in api:
            self.config.api.port = api["port"]
        for key, value in capture.items():
            setattr(self.config.capture, key, value)
        for key, value in privacy.items():
            setattr(self.config.privacy, key, value)

        if self.config_path is not None:
            save_config(self.config, self.config_path)

        return 200, {"ok": True, "settings": _settings_payload(self.config)}

    def get_privacy_rules(self) -> tuple[int, dict[str, Any]]:
        return 200, {
            "ok": True,
            "rules": list_all_privacy_rules(self.config.db_path),
        }

    def post_privacy_rule(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            entity_type, pattern, action = _validate_privacy_rule_payload(payload)
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

        rule = insert_privacy_rule(
            self.config.db_path,
            entity_type,
            pattern,
            action,
            _now_rfc3339_utc(),
        )
        return 201, {"ok": True, "rule": rule}

    def delete_privacy_rule(self, rule_id: int) -> tuple[int, dict[str, Any]]:
        if delete_privacy_rule(self.config.db_path, rule_id):
            return 200, {"ok": True, "deleted": True}
        return 404, {"ok": False, "error": "privacy rule not found"}

    def pause_tracking(self) -> tuple[int, dict[str, Any]]:
        self.tracking_paused = True
        return 200, {"ok": True, "paused": True}

    def resume_tracking(self) -> tuple[int, dict[str, Any]]:
        self.tracking_paused = False
        return 200, {"ok": True, "paused": False}

    def get_tracking_status(self) -> tuple[int, dict[str, Any]]:
        return 200, {"ok": True, "paused": self.tracking_paused}

    def _normalize_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")

        observed_at = _parse_rfc3339_utc(
            _required_str(payload, "observed_at"), "observed_at"
        )

        source = _required_str(payload, "source")
        if source not in ALLOWED_SOURCES:
            raise ValueError("source is not allowed")

        kind = _required_str(payload, "kind")
        if kind not in ALLOWED_KINDS:
            raise ValueError("kind is not allowed")

        entity_type = _required_str(payload, "entity_type")
        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise ValueError("entity_type is not allowed")
        _validate_event_contract(source, kind, entity_type)

        entity = _required_str(payload, "entity")
        raw_payload = payload.get("payload", {})
        if not isinstance(raw_payload, dict):
            raise ValueError("payload must be an object")

        return {
            "observed_at": observed_at,
            "received_at": _now_rfc3339_utc(),
            "source": source,
            "seq": _optional_int(payload.get("seq")),
            "kind": kind,
            "entity_type": entity_type,
            "entity": entity,
            "title": _stored_title(payload.get("title"), self.config),
            "payload": _stored_payload(raw_payload, self.config),
        }

    def _apply_privacy_rules(self, event: dict[str, Any]) -> dict[str, Any] | None:
        action = _privacy_action(
            list_privacy_rules(self.config.db_path, event["entity_type"]), event
        )
        if action == "drop":
            return None
        if action == "mask":
            return _masked_event(event)
        return event


def create_http_server(
    config: LocalTraceConfig, service: LocalTraceService
) -> ThreadingHTTPServer:
    handler = _handler_for(service)
    server = ThreadingHTTPServer((LOOPBACK_HOST, config.api.port), handler)
    service.bind_host = str(server.server_address[0])
    service.bind_port = int(server.server_address[1])
    return server


def main() -> None:
    config_path = default_config().data_dir / "config.json"
    config = load_or_create_config(config_path)
    initialize_database(config.db_path)
    server = create_http_server(config, LocalTraceService(config, config_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _handler_for(service: LocalTraceService) -> type[BaseHTTPRequestHandler]:
    class LocalTraceHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path, query = _path_and_query(self.path)
            if path == "/":
                self._write_static(WEB_DIR / "index.html")
                return
            if path in {"/web/app.js", "/web/styles.css"}:
                self._write_static(WEB_DIR / Path(path).name)
                return
            if path == "/health":
                self._write_json(*service.get_health())
                return
            if path == "/events":
                self._write_json(*service.get_events(query))
                return
            if path == "/settings":
                self._write_json(*service.get_settings())
                return
            if path == "/privacy/rules":
                self._write_json(*service.get_privacy_rules())
                return
            if path == "/tracking/status":
                self._write_json(*service.get_tracking_status())
                return
            self._write_json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            path, _query = _path_and_query(self.path)
            try:
                payload = self._read_json_body()
            except json.JSONDecodeError:
                self._write_json(400, {"ok": False, "error": "invalid JSON"})
                return
            if path == "/events":
                self._write_json(*service.post_events(payload))
                return
            if path == "/settings":
                self._write_json(*service.post_settings(payload))
                return
            if path == "/privacy/rules":
                self._write_json(*service.post_privacy_rule(payload))
                return
            if path == "/tracking/pause":
                self._write_json(*service.pause_tracking())
                return
            if path == "/tracking/resume":
                self._write_json(*service.resume_tracking())
                return
            self._write_json(404, {"ok": False, "error": "not found"})

        def do_DELETE(self) -> None:
            path, _query = _path_and_query(self.path)
            prefix = "/privacy/rules/"
            if not path.startswith(prefix):
                self._write_json(404, {"ok": False, "error": "not found"})
                return
            try:
                rule_id = int(path.removeprefix(prefix))
            except ValueError:
                self._write_json(400, {"ok": False, "error": "invalid rule id"})
                return
            self._write_json(*service.delete_privacy_rule(rule_id))

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise json.JSONDecodeError("JSON body must be an object", "", 0)
            return payload

        def _write_json(self, status: int, body: dict[str, Any]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _write_static(self, path: Path) -> None:
            if not path.is_file() or path.parent != WEB_DIR:
                self._write_json(404, {"ok": False, "error": "not found"})
                return
            encoded = path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                STATIC_CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
            )
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return LocalTraceHandler


def _path_and_query(path: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(path)
    query = {
        key: values[-1]
        for key, values in parse_qs(parsed.query, keep_blank_values=False).items()
        if values
    }
    return parsed.path, query


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError("seq must be an integer")


def _settings_payload(config: LocalTraceConfig) -> dict[str, Any]:
    return {
        "api": {"host": LOOPBACK_HOST, "port": config.api.port},
        "capture": {
            "poll_ms": config.capture.poll_ms,
            "heartbeat_seconds": config.capture.heartbeat_seconds,
            "idle_cutoff_seconds": config.capture.idle_cutoff_seconds,
            "store_titles": config.capture.store_titles,
            "store_exe_path": config.capture.store_exe_path,
            "track_browser": config.capture.track_browser,
            "track_audio": config.capture.track_audio,
        },
        "privacy": {
            "default_title_storage": config.privacy.default_title_storage,
        },
    }


def _validate_settings_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("settings payload must be an object")

    allowed_sections = {"api", "capture", "privacy"}
    if set(payload) - allowed_sections:
        raise ValueError("unknown settings section")

    updates: dict[str, dict[str, Any]] = {"api": {}, "capture": {}, "privacy": {}}
    for section in allowed_sections:
        value = payload.get(section, {})
        if not isinstance(value, dict):
            raise ValueError(f"{section} settings must be an object")

    api = payload.get("api", {})
    if set(api) - {"port"}:
        raise ValueError("unknown api setting")
    if "port" in api:
        updates["api"]["port"] = _bounded_int(api["port"], "api.port", 1, 65535)

    capture = payload.get("capture", {})
    int_fields = {
        "poll_ms": (100, 86_400_000),
        "heartbeat_seconds": (1, 86_400),
        "idle_cutoff_seconds": (1, 86_400),
    }
    bool_fields = {
        "store_titles",
        "store_exe_path",
        "track_browser",
        "track_audio",
    }
    if set(capture) - set(int_fields) - bool_fields:
        raise ValueError("unknown capture setting")
    for key, (minimum, maximum) in int_fields.items():
        if key in capture:
            updates["capture"][key] = _bounded_int(
                capture[key], f"capture.{key}", minimum, maximum
            )
    for key in bool_fields:
        if key in capture:
            updates["capture"][key] = _bool_value(capture[key], f"capture.{key}")

    privacy = payload.get("privacy", {})
    if set(privacy) - {"default_title_storage"}:
        raise ValueError("unknown privacy setting")
    if "default_title_storage" in privacy:
        updates["privacy"]["default_title_storage"] = _bool_value(
            privacy["default_title_storage"], "privacy.default_title_storage"
        )

    return updates


def _validate_privacy_rule_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        raise ValueError("privacy rule payload must be an object")
    if set(payload) - {"entity_type", "pattern", "action"}:
        raise ValueError("unknown privacy rule field")

    entity_type = _required_str(payload, "entity_type")
    if entity_type not in {"app", "domain"}:
        raise ValueError("entity_type must be app or domain")
    pattern = _required_str(payload, "pattern").strip()
    action = _required_str(payload, "action")
    if action not in {"drop", "mask"}:
        raise ValueError("action must be drop or mask")
    return entity_type, pattern, action


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{label} is out of range")
    return value


def _bool_value(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _validate_event_contract(source: str, kind: str, entity_type: str) -> None:
    expected_source, expected_entity_type = EVENT_CONTRACTS[kind]
    if source != expected_source or entity_type != expected_entity_type:
        raise ValueError("source, kind, and entity_type combination is not allowed")


def _stored_title(value: Any, config: LocalTraceConfig) -> str | None:
    if not config.capture.store_titles and not config.privacy.default_title_storage:
        return None
    return value if isinstance(value, str) and value else None


def _stored_payload(
    payload: dict[str, Any], config: LocalTraceConfig
) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    for key, value in payload.items():
        if key in ALWAYS_FILTERED_PAYLOAD_FIELDS:
            continue
        if (
            key in TITLE_PAYLOAD_FIELDS
            and not config.capture.store_titles
            and not config.privacy.default_title_storage
        ):
            continue
        if key in EXE_PATH_FIELDS and not config.capture.store_exe_path:
            continue
        stored[key] = value
    return stored


def _privacy_action(rules: list[dict[str, str]], event: dict[str, Any]) -> str | None:
    matched_action = None
    for rule in rules:
        if not _rule_matches(rule, event):
            continue
        if rule["action"] == "drop":
            return "drop"
        if rule["action"] == "mask":
            matched_action = "mask"
    return matched_action


def _rule_matches(rule: dict[str, str], event: dict[str, Any]) -> bool:
    entity_type = str(event["entity_type"])
    entity = str(event["entity"])
    pattern = rule["pattern"]

    if rule["entity_type"] != entity_type:
        return False
    if entity_type == "domain":
        return _domain_matches(entity, pattern)
    return entity.casefold() == pattern.casefold()


def _domain_matches(entity: str, pattern: str) -> bool:
    entity_value = entity.casefold().rstrip(".")
    pattern_value = pattern.casefold().rstrip(".")
    return entity_value == pattern_value or entity_value.endswith(f".{pattern_value}")


def _masked_event(event: dict[str, Any]) -> dict[str, Any]:
    masked = dict(event)
    masked["entity"] = "__hidden__"
    masked["title"] = None
    masked["payload"] = {
        key: value
        for key, value in event["payload"].items()
        if key not in MASKED_PAYLOAD_FIELDS
    }
    return masked


def _parse_rfc3339_utc(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be RFC3339 UTC")
    return (
        parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _now_rfc3339_utc() -> str:
    return _format_rfc3339_utc(datetime.now(UTC))


def _format_rfc3339_utc(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
