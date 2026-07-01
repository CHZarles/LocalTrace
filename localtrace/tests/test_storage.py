from pathlib import Path

from localtrace_core.storage import initialize_database, table_names


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


def test_schema_initialization_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "localtrace.db"

    initialize_database(db_path)
    initialize_database(db_path)

    assert {"events", "privacy_rules"}.issubset(table_names(db_path))
