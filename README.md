# LabGuard
Permission-based computer-lab monitoring and incident management.

## Components
- `apps/web`: Next.js + TypeScript dashboard.
- `services/api`: FastAPI REST API.
- `agent`: cross-platform Python agent using psutil, with Windows and Ubuntu/Linux support.
- PostgreSQL: durable storage.

## Supported lab environments

- The primary deployment is an approved central API on the college Ethernet/LAN. Internet access is not needed for normal telemetry once installed.
- For dual boot, install/configure the agent separately in Windows and Ubuntu. Only the currently booted OS reports.
- Windows 10/11 x64 and Ubuntu LTS x64 are the initial supported targets. Validate exact OS editions/builds and Python/runtime compatibility during the pilot; do not promise support for every historical Windows release.
- Ethernet-connected lab PCs send outbound telemetry to a central API on the college LAN. Internet access is not required for a LAN deployment.
- For a dual-boot PC, install/configure the agent separately inside Windows and Ubuntu. Only the currently booted OS can report. Use the same registered physical-computer record only if the admin wants one combined history; record the currently running OS on each heartbeat.

Read `AGENTS.md` first, then `docs/PLATFORM_SUPPORT.md`, then `docs/PRD.md`, `ARCHITECTURE.md`, `PLATFORM_SUPPORT.md`, `SECURITY.md`, `DATABASE.md`, `API_CONTRACT.md`, `AGENT_SPEC.md`, `UI_UX.md`, `IMPLEMENTATION_PLAN.md`, `TESTING.md`, and `DEPLOYMENT.md`.

## MVP
Authenticated staff dashboard; labs/devices; unique revocable agent credentials; CPU/RAM/disk telemetry; server-side online/stale/offline state; charts; threshold/missed-heartbeat alerts; incident lifecycle; CSV reports; audit trail; tests and deployment docs.

## Explicit non-goals
No remote shell, remote control, shutdown, arbitrary command execution, screenshots, keystrokes, browser history, personal files, or covert installation. Obtain lab-administrator approval before installing agents.

## Project toolchain (M1, approved targets)

- Node.js 22 LTS (`apps/web/.nvmrc`; `engines: node 22.x`). CI builds with Node 22.
- Python 3.12 (`requires-python ==3.12.*` in `services/api` and `agent`). Do not use Python 3.14 as a project runtime.
- PostgreSQL 16 (`postgres:16` in `infra/docker-compose.yml`).
- Next.js 14 + TypeScript strict mode; FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2; `psutil` + `httpx` reserved for the M5+ agent.

## Local setup (M1 scaffold)

Prerequisites: Git, Node.js 22 LTS, Python 3.12, Docker Desktop (for PostgreSQL).

1. Copy the environment template and set a local-only password (never commit real secrets):
   - `cp .env.example .env`, then edit `POSTGRES_PASSWORD` inside `.env`.
2. Start PostgreSQL 16:
   - `cd infra && docker compose up -d && docker exec <db-container> pg_isready -U labguard -d labguard`
3. Backend API:
   - `cd services/api && python -m venv .venv && .venv/Scripts/python -m pip install -e .[dev]` (Windows; use `.venv/bin/python` on Ubuntu)
   - Run: `.venv/Scripts/python -m uvicorn labguard_api.main:app --host 127.0.0.1 --port 8000`
   - Verify: `curl http://127.0.0.1:8000/api/v1/health` returns HTTP 200 with `status`, `server_time`, `version`.
4. Frontend web shell:
   - `cd apps/web && npm ci && npm run dev`
   - Open `http://localhost:3000`; the `/health` page reads the API at runtime (`NEXT_PUBLIC_API_BASE`, default `http://localhost:8000`) and reports reachability instead of showing data when the API is stopped.
5. Agent skeleton (packaging only in M1 — no collection):
   - `cd agent && python -m venv .venv && .venv/Scripts/python -m pip install -e .[dev] && .venv/Scripts/pytest -q`

Verification commands: API `ruff check .`, `mypy src`, `pytest -q`; agent `pytest -q`; web `npm run lint`, `npm run typecheck`, `npm run build`; infra `docker compose config` (provide `POSTGRES_PASSWORD` in env when validating).
