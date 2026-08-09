import os
from pathlib import Path

os.environ["DATABASE_PATH"] = str(Path(__file__).parent / "test_uptime.db")
os.environ["CHECK_INTERVAL_SECONDS"] = "3600"

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    database = Path(os.environ["DATABASE_PATH"])
    if database.exists():
        database.unlink()
    yield
    if database.exists():
        database.unlink()


@pytest.mark.asyncio
async def test_monitor_records_an_up_check_when_created(monkeypatch):
    async def fake_get(self, url, timeout):
        return Response(200, request=__import__("httpx").Request("GET", url))

    class StubClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, url, timeout):
            return await fake_get(self, url, timeout)

    monkeypatch.setattr("app.monitoring.httpx.AsyncClient", StubClient)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/api/monitors", json={"url": "https://example.com"})
            assert created.status_code == 201
            assert created.json()["status"] == "up"
            assert created.json()["latest_check"]["status_code"] == 200

            listed = await client.get("/api/monitors")
            assert listed.json()["monitors"][0]["url"] == "https://example.com"
            assert listed.json()["monitors"][0]["status"] == "up"


@pytest.mark.asyncio
async def test_monitor_records_a_failed_check_when_created(monkeypatch):
    import httpx

    async def fake_get(self, url, timeout):
        raise httpx.ConnectError("Connection refused", request=httpx.Request("GET", url))

    class StubClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, url, timeout):
            return await fake_get(self, url, timeout)

    monkeypatch.setattr("app.monitoring.httpx.AsyncClient", StubClient)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/api/monitors", json={"url": "http://bad.example.invalid"})
            body = created.json()
            assert created.status_code == 201
            assert body["status"] == "down"
            assert body["latest_check"]["status_code"] is None
            assert body["latest_check"]["error"]
