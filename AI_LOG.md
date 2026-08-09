# AI Collaboration Log

## AI tech stack

This exercise was built in the Codex desktop app with **OpenAI Codex (GPT-5)**.

## Representative prompts that shipped it

### Product boundary

> Build a strict-MVP uptime monitor for a few dozen HTTP(S) URLs.
>
> Required behavior:
> - Let a user register a URL.
> - Run a check immediately on registration, then every 60 seconds.
> - Store the HTTP status code, response time, timestamp, and any request error.
> - Return each monitor with its latest derived state: up, down, or pending.
>
> Implementation approach:
> - Use FastAPI, asyncio, httpx, and SQLite.
> - Start one background scheduler with the FastAPI app lifecycle.
> - Use one shared async HTTP client and a semaphore so only a bounded number of checks run at once.
> - Keep database writes from blocking in-flight HTTP checks.
>
> Constraints:
> - Keep the backend understandable as one process.

>
> Include tests for a successful HTTP response and a connection failure.

### UI direction

> Update the dashboard to be simple, functional, and easy to demo.
>
> Design constraints:
> - Use a white and light-blue visual system with no gradients.
> - Provide a URL form and a live monitor table.
> - Show URL, current status, latest response time, last-check time, and errors.
> - Include Check now and Remove actions.
> - Refresh displayed monitor data automatically.
>
> Use React and CSS only; do not introduce a component library.

### Architecture correction

> Refactor the implementation back to the assignment's strict-MVP scope. Keep one FastAPI process with a small bounded async scheduler and SQLite persistence. Remove the extra coordination components, but preserve immediate checks, periodic checks, stored history, and the current dashboard behavior. The result must be easy to explain and start locally with one command.

### Delivery brief

> Containerize the backend and frontend so docker compose up --build starts the complete application.
>
> Acceptance criteria:
> - Keep backend and frontend in their own folders.
> - Persist SQLite in a Docker volume.
> - Serve the built frontend through Nginx and route /api to FastAPI.
> - Document exact healthy and intentionally broken URL verification steps.
> - Write the README from the agreed architecture, setup flow, and deployment sketch.

## Course correction

Codex initially started adding extra dependencies such as Redis and separate processing pieces. That is a fair direction once the monitoring volume needs to scale, but for a few dozen URLs it was more architecture than the product needed. I wanted the base MVP working first, so I asked Codex to strip it back to one backend process, a small async loop, and persistent SQLite storage. That was enough for the job and much easier to run and explain.

That got the project back to the MVP I actually wanted:

~~~text
React dashboard -> FastAPI -> SQLite
                    |
                    +-> immediate and periodic HTTP checks
~~~

Codex did the heavy implementation and iteration; I made the calls on scope, architecture, interaction design, and when to simplify. I also had Codex write the README from those decisions, including the local verification steps and deployment sketch.
