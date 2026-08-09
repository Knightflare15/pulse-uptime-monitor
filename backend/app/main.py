import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .database import get_connection, initialize_database, uses_postgres
from .monitoring import (
    CHECK_INTERVAL_SECONDS,
    check_monitor,
    get_monitor,
    list_checks,
    list_monitor_rows,
    next_check_time,
    reschedule_monitor,
    run_scheduler,
    utc_now,
)
from .schemas import HealthCheck, Monitor, MonitorCreate, MonitorList


def to_health_check(row: dict) -> dict | None:
    if row.get("check_id") is None and row.get("id") is None:
        return None
    return {
        "id": row.get("check_id", row.get("id")),
        "status_code": row["status_code"],
        "response_time_ms": row["response_time_ms"],
        "checked_at": row["checked_at"],
        "error": row["error"],
    }


def to_monitor(row: dict) -> dict:
    latest_check = to_health_check(row)
    monitor_status = row.get("status") or "pending"
    if latest_check is None:
        monitor_status = "pending"
    return {
        "id": row["monitor_id"],
        "url": row["url"],
        "created_at": row["created_at"],
        "status": monitor_status,
        "latest_check": latest_check,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    stop_event = asyncio.Event()
    scheduler = asyncio.create_task(run_scheduler(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await scheduler


app = FastAPI(title="Pulse Uptime Monitor", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/monitors", response_model=MonitorList)
def list_monitors() -> dict:
    return {"monitors": [to_monitor(row) for row in list_monitor_rows()]}


@app.post("/api/monitors", response_model=Monitor, status_code=status.HTTP_201_CREATED)
async def create_monitor(payload: MonitorCreate) -> dict:
    url = str(payload.url).rstrip("/") or str(payload.url)
    now = utc_now()
    interval_seconds = payload.interval_seconds or CHECK_INTERVAL_SECONDS
    first_scheduled_check = next_check_time(interval_seconds)
    try:
        with get_connection() as connection:
            if uses_postgres():
                cursor = connection.execute(
                    """
                    INSERT INTO monitors (url, created_at, interval_seconds, next_check_at)
                    VALUES (?, ?, ?, ?) RETURNING id
                    """,
                    (url, now, interval_seconds, first_scheduled_check),
                )
                monitor_id = cursor.fetchone()["id"]
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO monitors (url, created_at, interval_seconds, next_check_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (url, now, interval_seconds, first_scheduled_check),
                )
                monitor_id = cursor.lastrowid
    except Exception as exc:
        if (
            "UNIQUE constraint failed" in str(exc)
            or "duplicate key value violates unique constraint" in str(exc)
        ):
            raise HTTPException(status_code=409, detail="This URL is already monitored") from exc
        raise

    await check_monitor(monitor_id, url)
    row = next(item for item in list_monitor_rows() if item["monitor_id"] == monitor_id)
    return to_monitor(row)


@app.post("/api/monitors/{monitor_id}/check", response_model=Monitor)
async def run_check_now(monitor_id: int) -> dict:
    monitor = get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await check_monitor(monitor_id, monitor["url"])
    reschedule_monitor(monitor_id, monitor["interval_seconds"])
    row = next(item for item in list_monitor_rows() if item["monitor_id"] == monitor_id)
    return to_monitor(row)


@app.get("/api/monitors/{monitor_id}/checks", response_model=list[HealthCheck])
def monitor_history(monitor_id: int, limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    if not get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    return [to_health_check(row) for row in list_checks(monitor_id, limit)]


@app.delete("/api/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(monitor_id: int) -> Response:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
