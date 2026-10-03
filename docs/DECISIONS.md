# Architecture decision log

Record date, context, decision, and consequences for new decisions.

## ADR-001 — Per-device Python agent
**Status:** Proposed. Each authorized PC runs a read-only agent and sends outbound telemetry. This enables CPU/RAM/disk metrics but requires installation approval, unique credentials, packaging, and uninstall documentation.

## ADR-002 — FastAPI
**Status:** Proposed. Python REST API with typed schemas. Web and API are separately deployable.

## ADR-003 — PostgreSQL
**Status:** Proposed. Relational records, constraints, transactions, and reports fit the domain. Schema changes require migrations.

## ADR-004 — Polling first
**Status:** Proposed. Start with dashboard polling because it is simpler and likely sufficient for a small lab. Reassess only after measuring need.

## ADR-005 — No remote control
**Status:** Fixed boundary. No remote shell, arbitrary commands, shutdown, or autonomous repair.

## ADR-006 — M1 pinned toolchain and scaffold
**Status:** Accepted (M1). Node.js 22 LTS, Python 3.12, PostgreSQL 16, Next.js 14 + TypeScript strict, FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2. Consequences: CI pins these versions; the ambient machine runtimes (Node 24, Python 3.14) must not be used as project targets; Python version split on dev machines is resolved by `requires-python ==3.12.*` and venvs per package.

## ADR-007 — M2 authentication, sessions, RBAC, and admin bootstrap
**Status:** Accepted (M2). Implemented in `services/api` (`security.py`, `routers/auth.py`, `deps.py`, `routers/labs.py`), migrated by `0001_m2_core`, tested on SQLite (35 tests) and verified live against PostgreSQL 16.
- Passwords: bcrypt cost 12 (`BCRYPT_ROUNDS=12`). Passwords over 72 bytes are rejected with 422, never truncated. Verification failures return a uniform 401 that reveals nothing about which check failed.
- Sessions: 256-bit opaque tokens (`secrets.token_urlsafe(32)`); only the SHA-256 hex digest is stored (`user_sessions.token_hash`). Sessions expire after 12 hours (`SESSION_TTL`) and are revoked by setting `revoked_at` on logout. Every request re-checks revocation, expiry, and that the user still exists and is active.
- Transport: browser cookie `labguard_session` with `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure=False`; API clients may send the same token as `Authorization: Bearer`. `Secure` stays off only until TLS is configured (M9); `SameSite=Lax` is the current and only CSRF baseline — there are no CSRF tokens or Origin checks.
- Login throttling: max 20 attempts per 60 seconds per client IP, counted for every login POST (success or failure); excess returns 429 `RATE_LIMITED`. The buckets are per-process and in-memory, so they are not shared across multiple API workers.
- RBAC: global roles `admin`/`staff`/`viewer`. Lab creation is global-admin-only. Other users see only active labs they belong to; anything else (missing, inactive, or non-member lab, including on manager-only membership endpoints) returns 404 `LAB_NOT_FOUND` so membership cannot be probed. Lab managers are global admins or members with the lab `admin` role; members without it get 403 on management actions.
- Deactivation: `users.is_active=false` blocks login and invalidates existing sessions through the per-request active-account check. Session rows are not proactively marked revoked.
- Bootstrap: `POST /api/v1/auth/bootstrap` creates the first global admin (role forced to `admin`) only when zero users exist; afterwards it returns 403 `BOOTSTRAP_CLOSED`. The count-then-insert race is closed on PostgreSQL with a transaction-scoped advisory lock (`pg_advisory_xact_lock`), applied only when the session dialect is PostgreSQL; on other databases the check-then-insert runs without the lock.
- Consequences: single-process deployment assumption for throttling; TLS (M9) required before `Secure` can be enabled; no user self-registration or admin user-management endpoints in M2.

## ADR-008 — M3 device identity, lab-scoped management, and write-only audit log
**Status:** Accepted (M3). Implemented in `services/api` (`routers/devices.py`, `audit.py`, `schemas.py` device models, `deps.py:get_visible_device`, `errors.py:device_not_found`), migrated by `0002_m3_audit_logs` (adds `audit_logs` only; the `devices` table from M2 needed no schema change), tested with 12 device tests plus a migration upgrade/downgrade test, and verified live against PostgreSQL 16.
- Write roles and lab scoping: device reads follow M2 lab visibility (global admin sees all active-lab devices; other users only devices in active labs they belong to). Device writes (register, patch) require lab managers — global admins or members holding the lab `admin` role; members without that role get 403. Callers without any membership get the same 404 as for a missing lab/device, so neither lab membership nor device IDs can be probed. A `lab_id` list filter pointing at an invisible lab returns 404, never an empty list.
- Hostname normalization and uniqueness: device identity is the (`lab_id`, `hostname`) pair with a database unique constraint. Hostnames are stored stripped and lowercased and must match `[a-z0-9][a-z0-9._-]*` (max 255 chars), so `SMOKE-PC-01` and `smoke-pc-01` collide with 409 `DEVICE_EXISTS` while the same hostname in another lab is a different device. A lost concurrent-registration race also reports 409 instead of failing or duplicating, via the `IntegrityError` handler. List search `q` is a case-insensitive substring match on hostname only (LIKE-escaped), ordered by hostname then id.
- Identity immutability: `lab_id` and `hostname` have no representation in the PATCH schema, so they cannot be changed after registration; unknown fields are ignored by Pydantic defaults, never applied. Only `display_name`, `platform`, `agent_version`, and `is_active` are patchable. Deactivation is the delete path (no device delete endpoint); deactivated devices stay visible to authorized callers so managers can re-enable them.
- Audit scope and transactions: `audit_logs` records `device.registered`, `device.updated`, `device.deactivated`, and `device.reactivated` with the acting user, entity type/id, and metadata limited to `hostname`, `lab_id`, `is_active`, `changed`, and the registration-supplied device fields — never credentials or secrets. Rows are flushed in the same transaction as the device change (failed requests leave no stray rows); no-op patches write no row. There is no audit-read endpoint in M3.
- No device credentials in M3: the router never issues, accepts, or returns per-device secrets; `last_seen_at` stays null until the M4 heartbeat. Enrollment tokens, credential revocation, and heartbeat auth are explicitly deferred to M4.
- Consequences: device administration is available to lab managers through the API with a tamper-evident lifecycle trail, but agents cannot yet enroll and no telemetry flows; the dashboard has no device UI until M6.

## ADR-009 — M4 device enrollment, agent authentication, and heartbeat ingestion
**Status:** Accepted (M4). Implemented in `services/api` (`routers/devices.py` enrollment/revocation, `routers/agent.py` heartbeat, `deps.py:get_current_device`, `security.py:device-token` helpers, `errors.py:device_unauthenticated`, `audit.py` credential events), migrated by `0003_m4_enrollment_heartbeat` (adds `agent_credentials`, `metrics`, `metric_volumes`; `0001`/`0002` untouched), tested with enrollment/heartbeat tests plus a migration upgrade/downgrade test, and verified live against PostgreSQL 16.
- Reusable bearer credentials, not single-use enrollment tokens: an issued credential works for heartbeats until revoked, even if more credentials are issued later for the same device. Rotation is revoke-then-issue.
- Raw credential shown once: the issuance response returns the opaque token exactly once; only its SHA-256 hex digest is stored (`token_hash`, unique). Raw tokens never appear in storage, logs, audit rows, or later responses. A hash collision reports `503 TOKEN_COLLISION` and the client retries.
- No enforced expiry: `expires_at` exists but stays NULL until an expiration policy is defined; revocation is the only lifecycle mechanism.
- Multiple active credentials allowed: several credentials may be live per device; revoke-agent revokes all applicable active credentials at once and is idempotent (zero-revoke writes no audit row, mirroring the M3 no-op-patch rule).
- Credential-bound heartbeat identity: the heartbeat device comes from the authenticated credential's `device_id`; body identity fields are accepted but ignored and cannot override it. Each accepted heartbeat writes one `metrics` row plus `metric_volumes` rows, stamps `recorded_at`/`last_seen_at`/`last_used_at` from the server clock, and refreshes reported platform/agent version, all in one transaction.
- Uniform 401: missing, unknown, revoked, or expired tokens, and credentials bound to deactivated devices or inactive labs, all return the same `401 UNAUTHENTICATED` (`Invalid or revoked device credential.`).
- Heartbeats write no audit rows; enrollment and revocation write `device.enrollment_issued` / `device.credential_revoked` rows (metadata limited to `hostname`, `lab_id`, `credential_id`) in the same transaction as the change.
- Heartbeat rate limiting is deferred to M9.
- Consequences: agents can now enroll and submit telemetry, but there is still no telemetry-history endpoint, dashboard, alerts, or incidents (M6/M7); per the dual-boot note, each heartbeat reports the currently running OS, so stored platform/version tracks the latest reporter.

## Open decisions
- Actual lab OS/version and PC count.
- Internal LAN versus cloud.
- Sampling interval and stale/offline thresholds.
- College approval and permitted metrics.
- Retention policy.
