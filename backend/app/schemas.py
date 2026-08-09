from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class MonitorCreate(BaseModel):
    url: HttpUrl
    interval_seconds: int | None = Field(default=None, ge=10, le=3600)

    @field_validator("url")
    @classmethod
    def only_http_urls(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("Only http and https URLs are supported")
        return value


class HealthCheck(BaseModel):
    id: int
    status_code: int | None
    response_time_ms: float | None
    checked_at: datetime
    error: str | None


class Monitor(BaseModel):
    id: int
    url: str
    created_at: datetime
    status: Literal["up", "down", "pending"]
    latest_check: HealthCheck | None


class MonitorList(BaseModel):
    monitors: list[Monitor]