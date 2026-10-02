# Implementation plan

Build in small milestones. Do not ask OpenCode to generate the whole application in one pass.

## M0 — Repository audit
Inspect git status, existing code, package managers, Node/Python versions, tests, lab OS, network, and deployment assumptions. Report conflicts/missing decisions. Do not overwrite existing work.

## M1 — Scaffold
Create web/API/agent structure only if needed. Add env example, gitignore, lint/format/type checks, local PostgreSQL setup, API health route, web shell, and CI checks. Exit: clean setup and successful builds.

## M2 — Database and auth
Create SQLAlchemy models and Alembic initial migration. Choose secure session/auth strategy. Add safe admin bootstrap; never ship a default public password. Test unauthenticated and role-restricted access.

## M3 — Labs and devices
Implement lab/device CRUD, validation, pagination, search/filter, and audit events. Exit: admin can create lab and register device.

## M4 — Enrollment and heartbeat API
Generate high-entropy per-device token, store hash, show raw token once, support revocation, validate heartbeat payload, set server timestamps, and write transactionally. Test invalid/revoked tokens and device binding.

## M5 — Agent
Implement config validation, metric collection, HTTP transport, timeouts, bounded retry/backoff, safe logging, and shutdown. Test collection and transport. Exit: real development machine reports to API.

## M6 — Dashboard and history
Implement overview, device list/detail, summary API, bounded history endpoint, charts, and loading/empty/error states. Exit: real telemetry appears.

## M7 — Alerts
Implement configurable CPU/RAM/disk thresholds, missing-heartbeat detection, deduplication, acknowledge/resolve, and audit events. Use one scheduler strategy and avoid duplicate workers.

## M8 — Incidents and reports
Implement incident lifecycle, assignment, resolution notes, audit trail, filters, and authorized CSV export with safe escaping.

## M9 — Hardening/deployment
CORS, cookies/CSRF as relevant, rate limits, request bounds, health/readiness, backups, restore instructions, retention only after policy approval, smoke tests.

## M10 — College pilot
Obtain approval. Test on one PC, then two or three, then a small subset. Check network reachability and endpoint protection. Document install/uninstall, revocation, failure recovery, and feedback.

## Report after every milestone
Summary, files changed, commands run, actual test results, security/privacy notes, known gaps, next milestone. Do not proceed with failing tests or unresolved security-sensitive decisions.

## Cross-platform college pilot (added release milestone)
The lab administrator will authorize the pilot. Record exact Windows edition/version/build and Ubuntu version. Test one Windows PC and one Ubuntu PC first, then a dual-boot PC if available, then two or three PCs, then a small subset. Confirm Ethernet/LAN reachability, firewall rules, endpoint-protection compatibility, startup after reboot, credential revocation, and recovery after network/server outages. Document OS-specific installation and removal. Do not claim cross-platform readiness until the test matrix in `docs/PLATFORM_SUPPORT.md` passes on real systems.
