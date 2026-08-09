from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import DATABASE_PATH, get_connection, initialize_database
from app.monitoring import claim_due_monitors


@pytest.fixture(autouse=True)
def clean_database():
    database = Path(DATABASE_PATH)
    if database.exists():
        database.unlink()
    yield
    if database.exists():
        database.unlink()


def test_scheduler_claims_a_due_monitor_once_and_reschedules_it():
    initialize_database()
    due_now = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO monitors (url, created_at, interval_seconds, next_check_at)
            VALUES (?, ?, ?, ?)
            """,
            ("https://scheduled.example", due_now, 60, due_now),
        )
        monitor_id = cursor.lastrowid

    due = claim_due_monitors()
    assert due == [{"id": monitor_id, "url": "https://scheduled.example", "interval_seconds": 60}]
    assert claim_due_monitors() == []

    with get_connection() as connection:
        next_check_at = connection.execute(
            "SELECT next_check_at FROM monitors WHERE id = ?", (monitor_id,)
        ).fetchone()["next_check_at"]
    assert next_check_at > due_now
