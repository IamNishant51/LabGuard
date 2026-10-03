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

## Database and auth (M2)

M2 adds users, labs, lab memberships, device identity records, and database-backed session auth (see `docs/DATABASE.md`, `docs/API_CONTRACT.md`, and ADR-007 in `docs/DECISIONS.md`).

Environment (API):
- `DATABASE_URL` (required, fail-fast): e.g. `postgresql+psycopg://labguard:<password>@localhost:5432/labguard`. Never commit real passwords; keep them in `.env` (see `.env.example`).
- `POSTGRES_PORT` (infra, default `5432`): host-side port mapped to the container. Change it if another PostgreSQL already listens on 5432 on the host.

Migrations (from `services/api`, with `DATABASE_URL` exported):
- Apply: `.venv/Scripts/python -m alembic upgrade head` (use `.venv/bin/python` on Ubuntu).
- Verify schema matches models: `alembic check` — must report "No new upgrade operations detected".
- Show applied revision: `alembic current`.
- Offline SQL preview (still requires `DATABASE_URL` to be set): `alembic upgrade head --sql`.

Initial-admin bootstrap (run once against a fresh database):
1. Start the API with `DATABASE_URL` pointing at the migrated database.
2. `POST /api/v1/auth/bootstrap` with `{ "email", "password" (min 12 chars, max 72 bytes), "display_name" }` returns `201` and the admin user.
3. Any later call returns `403 BOOTSTRAP_CLOSED`. Further users, labs, and memberships are managed through the lab endpoints (labs are created by the admin; see `docs/API_CONTRACT.md`).

Security properties and limits (M2):
- Bcrypt cost-12 password hashing; opaque 256-bit session tokens, SHA-256 hash at rest, 12-hour expiry, logout revocation.
- Browser cookie `labguard_session`: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure=False` until TLS is configured — `SameSite=Lax` is the current and only CSRF baseline (no CSRF tokens or Origin checks).
- Login is throttled per client IP (20 attempts / 60 s, per-process in-memory — not shared across API workers).
- Deactivated accounts cannot log in and their sessions are rejected by the per-request active-account check.
- Bootstrap concurrency is serialized by a PostgreSQL advisory lock; on other databases the check-then-insert runs without that lock.

## Device management and audit log (M3)

M3 adds lab-scoped device identity records and a write-only audit trail (see `docs/API_CONTRACT.md` Devices section and ADR-008 in `docs/DECISIONS.md`):

- `POST /api/v1/devices` (lab managers only) registers a device; identity is the (`lab_id`, `hostname`) pair, hostnames are stored lowercased, duplicates report `409 DEVICE_EXISTS`.
- `GET /api/v1/devices` lists with `lab_id`, `q` (hostname substring), and `is_active` filters plus pagination; `GET /api/v1/devices/{id}` retrieves one; `PATCH /api/v1/devices/{id}` (lab managers only) edits metadata or flips `is_active`. Identity fields cannot be changed. Cross-lab access reads as `404 DEVICE_NOT_FOUND`.
- Every registration, metadata change, deactivation, and reactivation writes an `audit_logs` row in the same transaction (migration `0002_m3_audit_logs`); there is no audit-read endpoint yet, and no device credentials or enrollment tokens exist until M4.

Run the M3 tests from `services/api`: `.venv/Scripts/python -m pytest -q tests/test_devices.py tests/test_migration.py` (use `.venv/bin/python` on Ubuntu).

## Device enrollment and heartbeat (M4)

M4 adds per-device bearer credentials and authenticated telemetry ingestion (see `docs/API_CONTRACT.md` Devices/Agent sections and ADR-009 in `docs/DECISIONS.md`):

- `POST /api/v1/devices/{id}/enrollment-token` (lab managers only) issues a bearer token; the raw token is returned exactly once and only its SHA-256 hash is stored. Credentials are reusable until revoked; `expires_at` stays NULL (no expiry enforced). Hash collision reports `503 TOKEN_COLLISION`.
- `POST /api/v1/devices/{id}/revoke-agent` (lab managers only) revokes all active credentials for the device; idempotent when nothing is active. Both endpoints write audit rows (`device.enrollment_issued`, `device.credential_revoked`) without secrets.
- `POST /api/v1/agent/heartbeat` accepts telemetry with a device bearer token only — no user session. Identity comes from the credential; body identity fields are ignored. Each accepted heartbeat writes one `metrics` row plus `metric_volumes` rows, stamps `recorded_at`/`last_seen_at`/`last_used_at` from the server clock, and refreshes reported platform/agent version in a single transaction. Auth failures are a uniform `401 UNAUTHENTICATED`; heartbeats write no audit rows. Rate limiting is deferred to M9.

Run the M4 tests from `services/api`: `.venv/Scripts/python -m pytest -q tests/test_enrollment.py tests/test_migration.py` (use `.venv/bin/python` on Ubuntu). Run the agent checks from `agent/`: `.venv/Scripts/pytest -q`.
