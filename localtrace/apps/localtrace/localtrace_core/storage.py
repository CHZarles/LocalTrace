from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              observed_at TEXT NOT NULL,
              received_at TEXT NOT NULL,
              source TEXT NOT NULL,
              seq INTEGER,
              kind TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity TEXT NOT NULL,
              title TEXT,
              payload_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_observed_at
              ON events(observed_at);
            CREATE INDEX IF NOT EXISTS idx_events_source_kind_observed_at
              ON events(source, kind, observed_at);

            CREATE TABLE IF NOT EXISTS privacy_rules (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_type TEXT NOT NULL,
              pattern TEXT NOT NULL,
              action TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_privacy_rules_entity
              ON privacy_rules(entity_type, pattern);
            """
        )


def table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def insert_event(db_path: Path, event: dict[str, Any]) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
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
                event["observed_at"],
                event["received_at"],
                event["source"],
                event.get("seq"),
                event["kind"],
                event["entity_type"],
                event["entity"],
                event.get("title"),
                json.dumps(event.get("payload", {}), sort_keys=True),
            ),
        )
        return int(cursor.lastrowid)


def list_events(db_path: Path, filters: dict[str, str]) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if from_time := filters.get("from"):
        clauses.append("observed_at >= ?")
        params.append(from_time)
    if to_time := filters.get("to"):
        clauses.append("observed_at <= ?")
        params.append(to_time)
    if source := filters.get("source"):
        clauses.append("source = ?")
        params.append(source)
    if kind := filters.get("kind"):
        clauses.append("kind = ?")
        params.append(kind)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit = _limit(filters.get("limit"))
    params.append(limit)

    query = f"""
        SELECT
          id,
          observed_at,
          received_at,
          source,
          seq,
          kind,
          entity_type,
          entity,
          title,
          payload_json
        FROM events
        {where}
        ORDER BY observed_at ASC, id ASC
        LIMIT ?
    """

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "id": row[0],
            "observed_at": row[1],
            "received_at": row[2],
            "source": row[3],
            "seq": row[4],
            "kind": row[5],
            "entity_type": row[6],
            "entity": row[7],
            "title": row[8],
            "payload": json.loads(row[9]),
        }
        for row in rows
    ]


def _limit(raw: str | None) -> int:
    if raw is None:
        return 500
    try:
        value = int(raw)
    except ValueError:
        return 500
    return min(max(value, 1), 5000)
