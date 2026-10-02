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

## Open decisions
- Actual lab OS/version and PC count.
- Internal LAN versus cloud.
- Sampling interval and stale/offline thresholds.
- College approval and permitted metrics.
- Authentication/session approach and admin bootstrap.
- Retention policy.
- Staff access scoped by lab or globally.
