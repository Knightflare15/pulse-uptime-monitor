import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/data/uptime.db"))
DATABASE_URL = os.getenv("DATABASE_URL")


def uses_postgres() -> bool:
    return bool(DATABASE_URL and DATABASE_URL.startswith(("postgres://", "postgresql://")))


class DatabaseConnection:
    """Small adapter: SQLite is the local default; PostgreSQL is optional for deployment."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query: str, parameters=()):
        if uses_postgres():
            query = query.replace("?", "%s")
        return self.connection.execute(query, parameters)

    def executescript(self, script: str) -> None:
        if uses_postgres():
            for statement in script.split(";"):
                if statement.strip():
                    self.connection.execute(statement)
            return
        self.connection.executescript(script)


def _table_columns(connection: DatabaseConnection, table: str) -> set[str]:
    if uses_postgres():
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_monitor_columns(connection: DatabaseConnection) -> None:
    columns = _table_columns(connection, "monitors")
    definitions = {
        "interval_seconds": "INTEGER NOT NULL DEFAULT 60",
        "next_check_at": "TIMESTAMPTZ" if uses_postgres() else "TEXT",
        "last_status": "TEXT NOT NULL DEFAULT 'pending'",
        "last_status_code": "INTEGER",
        "last_response_time_ms": "DOUBLE PRECISION" if uses_postgres() else "REAL",
        "last_checked_at": "TIMESTAMPTZ" if uses_postgres() else "TEXT",
        "last_error": "TEXT",
        "last_check_id": "BIGINT" if uses_postgres() else "INTEGER",
    }
    for name, definition in definitions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE monitors ADD COLUMN {name} {definition}")


def initialize_database() -> None:
    if uses_postgres():
        schema = """
            CREATE TABLE IF NOT EXISTS monitors (
                id BIGSERIAL PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 60,
                next_check_at TIMESTAMPTZ,
                last_status TEXT NOT NULL DEFAULT 'pending',
                last_status_code INTEGER,
                last_response_time_ms DOUBLE PRECISION,
                last_checked_at TIMESTAMPTZ,
                last_error TEXT,
                last_check_id BIGINT
            );

            CREATE TABLE IF NOT EXISTS health_checks (
                id BIGSERIAL PRIMARY KEY,
                monitor_id BIGINT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
                status_code INTEGER,
                response_time_ms DOUBLE PRECISION,
                checked_at TIMESTAMPTZ NOT NULL,
                error TEXT
            );
        """
    else:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        schema = """
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 60,
                next_check_at TEXT,
                last_status TEXT NOT NULL DEFAULT 'pending',
                last_status_code INTEGER,
                last_response_time_ms REAL,
                last_checked_at TEXT,
                last_error TEXT,
                last_check_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS health_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id INTEGER NOT NULL,
                status_code INTEGER,
                response_time_ms REAL,
                checked_at TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
            );
        """

    with get_connection() as connection:
        if uses_postgres():
            connection.execute("SELECT pg_advisory_xact_lock(82430117)")
        connection.executescript(schema)
        _ensure_monitor_columns(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_health_checks_monitor_checked "
            "ON health_checks(monitor_id, checked_at DESC)"
        )


@contextmanager
def get_connection() -> Iterator[DatabaseConnection]:
    if uses_postgres():
        raw_connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    else:
        raw_connection = sqlite3.connect(DATABASE_PATH)
        raw_connection.row_factory = sqlite3.Row
        raw_connection.execute("PRAGMA foreign_keys = ON")

    connection = DatabaseConnection(raw_connection)
    try:
        yield connection
        raw_connection.commit()
    finally:
        raw_connection.close()
