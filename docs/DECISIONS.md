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

## Open decisions
- Actual lab OS/version and PC count.
- Internal LAN versus cloud.
- Sampling interval and stale/offline thresholds.
- College approval and permitted metrics.
- Retention policy.
