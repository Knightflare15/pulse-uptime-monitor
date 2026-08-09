import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from .database import get_connection, uses_postgres


CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
CHECK_CONCURRENCY = int(os.getenv("CHECK_CONCURRENCY", "20"))
SCHEDULER_POLL_SECONDS = float(os.getenv("SCHEDULER_POLL_SECONDS", "1"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_check_time(interval_seconds: int = CHECK_INTERVAL_SECONDS) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)).isoformat()


def record_check_result(
    monitor_id: int,
    status_code: int | None,
    response_time_ms: float | None,
    error: str | None,
) -> None:
    """Persist one immutable result and update the monitor's latest state."""
    checked_at = utc_now()
    latest_status = "up" if status_code is not None and 200 <= status_code < 400 else "down"

    with get_connection() as connection:
        if uses_postgres():
            row = connection.execute(
                """
                INSERT INTO health_checks (monitor_id, status_code, response_time_ms, checked_at, error)
                VALUES (?, ?, ?, ?, ?) RETURNING id
                """,
                (monitor_id, status_code, response_time_ms, checked_at, error),
            ).fetchone()
            check_id = row["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO health_checks (monitor_id, status_code, response_time_ms, checked_at, error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (monitor_id, status_code, response_time_ms, checked_at, error),
            )
            check_id = cursor.lastrowid

        connection.execute(
            """
            UPDATE monitors
            SET last_status = ?, last_status_code = ?, last_response_time_ms = ?,
                last_checked_at = ?, last_error = ?, last_check_id = ?
            WHERE id = ? AND (last_checked_at IS NULL OR last_checked_at <= ?)
            """,
            (
                latest_status,
                status_code,
                response_time_ms,
                checked_at,
                error,
                check_id,
                monitor_id,
                checked_at,
            ),
        )


async def check_monitor(
    monitor_id: int,
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Check one endpoint and persist its result."""
    started = time.perf_counter()
    status_code: int | None = None
    response_time_ms: float | None = None
    error: str | None = None

    try:
        if client is None:
            async with httpx.AsyncClient(follow_redirects=True) as owned_client:
                response = await owned_client.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        else:
            response = await client.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        status_code = response.status_code
        response_time_ms = round((time.perf_counter() - started) * 1000, 2)
    except httpx.HTTPError as exc:
        response_time_ms = round((time.perf_counter() - started) * 1000, 2)
        error = str(exc) or exc.__class__.__name__

    await asyncio.to_thread(record_check_result, monitor_id, status_code, response_time_ms, error)


def list_monitor_rows() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
              id AS monitor_id, url, created_at, last_status AS status,
              last_check_id AS check_id, last_status_code AS status_code,
              last_response_time_ms AS response_time_ms, last_checked_at AS checked_at,
              last_error AS error
            FROM monitors
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_monitor(monitor_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, url, created_at, interval_seconds FROM monitors WHERE id = ?", (monitor_id,)
        ).fetchone()
    return dict(row) if row else None


def list_checks(monitor_id: int, limit: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, status_code, response_time_ms, checked_at, error
            FROM health_checks
            WHERE monitor_id = ?
            ORDER BY checked_at DESC, id DESC
            LIMIT ?
            """,
            (monitor_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def reschedule_monitor(monitor_id: int, interval_seconds: int | None = None) -> None:
    with get_connection() as connection:
        if interval_seconds is None:
            row = connection.execute(
                "SELECT interval_seconds FROM monitors WHERE id = ?", (monitor_id,)
            ).fetchone()
            if not row:
                return
            interval_seconds = row["interval_seconds"]
        connection.execute(
            "UPDATE monitors SET next_check_at = ? WHERE id = ?",
            (next_check_time(interval_seconds), monitor_id),
        )


def claim_due_monitors() -> list[dict]:
    """Move due monitors to their next interval before running their checks."""
    now = utc_now()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, url, interval_seconds
            FROM monitors
            WHERE next_check_at IS NULL OR next_check_at <= ?
            ORDER BY id
            """,
            (now,),
        ).fetchall()
        monitors = [dict(row) for row in rows]
        for monitor in monitors:
            connection.execute(
                "UPDATE monitors SET next_check_at = ? WHERE id = ?",
                (next_check_time(monitor["interval_seconds"]), monitor["id"]),
            )
    return monitors


async def run_scheduler(stop_event: asyncio.Event) -> None:
    """Small in-process scheduler for the MVP's few-dozen-monitor workload."""
    semaphore = asyncio.Semaphore(CHECK_CONCURRENCY)

    async def bounded_check(monitor: dict, client: httpx.AsyncClient) -> None:
        async with semaphore:
            await check_monitor(monitor["id"], monitor["url"], client=client)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        while not stop_event.is_set():
            due_monitors = await asyncio.to_thread(claim_due_monitors)
            if due_monitors:
                await asyncio.gather(
                    *(bounded_check(monitor, client) for monitor in due_monitors),
                    return_exceptions=True,
                )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=SCHEDULER_POLL_SECONDS)
            except TimeoutError:
                pass
