from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import (
    LOOPBACK_HOST,
    LocalTraceConfig,
    default_config,
    load_or_create_config,
)
from .storage import initialize_database, insert_event, list_events, list_privacy_rules

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


class LocalTraceService:
    def __init__(self, config: LocalTraceConfig) -> None:
        self.config = config

    def get_health(self) -> tuple[int, dict[str, Any]]:
        return 200, {
            "ok": True,
            "service": "localtrace",
            "bind": {
                "host": LOOPBACK_HOST,
                "port": self.config.api.port,
            },
            "database": {
                "path": str(self.config.db_path),
                "exists": self.config.db_path.exists(),
            },
            "data_dir": str(self.config.data_dir),
        }

    def post_events(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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

    def _apply_privacy_rules(
        self, event: dict[str, Any]
    ) -> dict[str, Any] | None:
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
    return ThreadingHTTPServer((LOOPBACK_HOST, config.api.port), handler)


def main() -> None:
    config_path = default_config().data_dir / "config.json"
    config = load_or_create_config(config_path)
    initialize_database(config.db_path)
    server = create_http_server(config, LocalTraceService(config))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _handler_for(service: LocalTraceService) -> type[BaseHTTPRequestHandler]:
    class LocalTraceHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path, query = _path_and_query(self.path)
            if path == "/health":
                self._write_json(*service.get_health())
                return
            if path == "/events":
                self._write_json(*service.get_events(query))
                return
            self._write_json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            path, _query = _path_and_query(self.path)
            if path != "/events":
                self._write_json(404, {"ok": False, "error": "not found"})
                return
            try:
                payload = json.loads(
                    self.rfile.read(int(self.headers.get("Content-Length", "0")))
                )
            except json.JSONDecodeError:
                self._write_json(400, {"ok": False, "error": "invalid JSON"})
                return
            self._write_json(*service.post_events(payload))

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status: int, body: dict[str, Any]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
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
    return parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _now_rfc3339_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
