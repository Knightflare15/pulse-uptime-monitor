# Pulse - Uptime Monitor

A deliberately small uptime monitor for HTTP and HTTPS endpoints. It records each check's HTTP status code, response time, timestamp, and error, then shows the latest result in a React dashboard.

## One-line setup

~~~bash
docker compose up --build
~~~

Open [http://localhost:3000](http://localhost:3000). The FastAPI docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

Compose starts only two application services:

- **backend** - FastAPI, a small in-process scheduler, and a SQLite database stored in a named Docker volume.
- **frontend** - React dashboard served by Nginx.

## How it works

When a URL is added, the backend checks it immediately. A lightweight async loop then checks each registered URL every 60 seconds. The loop uses a shared HTTP client and a modest concurrency cap of 20, which is comfortably more than needed for a few dozen URLs.

~~~text
React dashboard -> FastAPI -> SQLite
                    |
                    +-> async HTTP checks every 60 seconds
~~~

The **Check now** button performs an immediate HTTP check for that monitor. The dashboard automatically reloads its displayed data every five seconds.

## Verify up and down states

1. Run docker compose up --build and open the dashboard.
2. Add https://example.com. It should appear as **up**, with an HTTP status and response time.
3. Add http://127.0.0.1:65534/does-not-exist. Nothing listens at that address from the backend container, so it should appear as **down** with a connection error.
4. Use **Check now** to repeat a check immediately, or wait about one minute for the next scheduled result.

Equivalent API calls:

~~~bash
curl -X POST http://localhost:8000/api/monitors -H "Content-Type: application/json" -d "{\"url\":\"https://example.com\"}"
curl -X POST http://localhost:8000/api/monitors -H "Content-Type: application/json" -d "{\"url\":\"http://127.0.0.1:65534/does-not-exist\"}"
curl http://localhost:8000/api/monitors
~~~

A result is **up** for an HTTP 2xx or 3xx response. Network errors and HTTP 4xx/5xx responses are **down**.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| POST | /api/monitors | Register a URL and run its first check. Optional interval_seconds is 10-3600. |
| GET | /api/monitors | List monitors with their latest status. |
| POST | /api/monitors/{id}/check | Run an immediate check. |
| GET | /api/monitors/{id}/checks | Return recent stored check history. |
| DELETE | /api/monitors/{id} | Stop monitoring a URL and remove its history. |

## Deployment sketch

For Azure, I would build the frontend and backend images, store them in Azure Container Registry, and run them together in one Azure Container App. The Nginx container would receive public HTTPS traffic and proxy /api requests to the FastAPI container. Azure Database for PostgreSQL would provide managed persistence through the existing DATABASE_URL setting.

~~~text
Azure Container Registry
          |
Internet -> Azure Container Apps ingress
                    |
        one Container App replica
          |-- Nginx frontend container
          +-- FastAPI backend + scheduler
                    |
        Azure Database for PostgreSQL
~~~

The backend would initially stay at one replica because the scheduler runs inside that process. Container Apps would handle HTTPS ingress, container revisions, and health-based restarts without adding those concerns to the application.

### Future scaling path

If demand grows, I would move the scheduler into its own Container App or scheduled job and then allow the stateless API containers to scale horizontally. PostgreSQL is already outside the application container, so API replicas can share the same durable database without changing the local MVP architecture.

## Local development and tests

~~~bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
~~~

## Project layout

~~~text
backend/   FastAPI API, async scheduler, SQLite persistence, and tests
frontend/  React/Vite dashboard, built and served by Nginx
docker-compose.yml
AI_LOG.md
~~~
