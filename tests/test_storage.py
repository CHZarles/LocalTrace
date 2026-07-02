import json
import sqlite3
from pathlib import Path

from localtrace_core.storage import (
    initialize_database,
    latest_events_by_source,
    table_names,
)


def test_schema_creates_raw_event_and_privacy_tables_only(tmp_path: Path) -> None:
    db_path = tmp_path / "localtrace.db"

    initialize_database(db_path)

    tables = table_names(db_path)
    assert "events" in tables
    assert "privacy_rules" in tables
    assert "blocks" not in tables
    assert "timeline_segments" not in tables
    assert "top_items" not in tables
    assert "reports" not in tables
    assert "review_notes" not in tables


def test_privacy_rules_schema_contains_documented_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "localtrace.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(privacy_rules)").fetchall()
        }

    assert {"id", "entity_type", "pattern", "action", "created_at"} <= columns


def test_schema_initialization_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "localtrace.db"

    initialize_database(db_path)
    initialize_database(db_path)

    assert {"events", "privacy_rules"}.issubset(table_names(db_path))


def test_latest_events_by_source_returns_timestamps_from_same_latest_row(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "localtrace.db"
    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO events (
              observed_at,
              received_at,
              source,
              seq,
              kind,
              entity_type,
              entity,
              title,
              payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-07-01T12:00:00.000Z",
                "2026-07-01T10:00:00.000Z",
                "browser_extension",
                1,
                "tab_active",
                "domain",
                "example.com",
                None,
                json.dumps({}),
            ),
        )
        conn.execute(
            """
            INSERT INTO events (
              observed_at,
              received_at,
              source,
              seq,
              kind,
              entity_type,
              entity,
              title,
              payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-07-01T11:00:00.000Z",
                "2026-07-01T11:00:00.000Z",
                "browser_extension",
                2,
                "tab_active",
                "domain",
                "example.org",
                None,
                json.dumps({}),
            ),
        )

    assert latest_events_by_source(db_path)["browser_extension"] == {
        "last_observed_at": "2026-07-01T11:00:00.000Z",
        "last_received_at": "2026-07-01T11:00:00.000Z",
    }
