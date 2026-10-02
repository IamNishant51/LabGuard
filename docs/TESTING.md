# Testing strategy

## Layers
- Backend unit tests: status calculation, threshold logic, validation, incident transitions.
- API integration tests: database-backed routes, authentication, authorization, migrations.
- Agent tests: metric mapping, configuration, transport, retries, secret redaction.
- Frontend tests: components, forms, status states, filters.
- E2E smoke: login → create lab/device → enroll agent → heartbeat → dashboard → alert → incident resolution.
- Manual pilot: network loss, stopped agent, server restart, credential revocation.

## Backend cases
- Missing, malformed, revoked, and valid agent credentials.
- Credential for device A cannot submit for device B.
- Percentages outside 0–100 and negative bytes rejected.
- Server time controls `last_seen_at`.
- Never-seen device is not online.
- Status boundaries tested exactly.
- Repeated heartbeat does not create duplicate active alerts.
- Role and cross-lab access denied as expected.
- Pagination bounds enforced.
- CSV handles commas, quotes, newlines, and formula-leading cells safely.

## Agent cases
Missing config; successful report; timeout; DNS/TLS error; 401/403; 429; 5xx; bounded backoff; inaccessible disk; shutdown; no secrets in logs; no remote command execution.

## Frontend cases
Loading, empty, error, populated, filtered-empty; useful API errors; search/filter composition; stale response handling; duplicate submit prevention; keyboard navigation; role-restricted navigation.

## Initial performance targets to measure, not promise
- Dashboard summary p95 below 500 ms on a documented pilot dataset/hardware.
- Paginated device list p95 below 500 ms.
- UI update within one polling interval plus request latency.
- Heartbeat normally completes within 3 seconds on the lab network.
Record hardware, data size, test command, and results. Do not claim targets met without measurements.

## Test data
Use synthetic names such as `DEMO-PC-001`. Clearly label seeded demo data. Never mix fake metrics into a real pilot without a visible demo-mode indicator.

## Cross-platform test matrix (added)
Run integration checks on actual Windows 10/11 x64 and supported Ubuntu LTS x64 targets. Record exact edition/release/build and outcome. Test Windows drive-letter volumes and Linux mount points/pseudo-filesystems. If dual boot uses one registered device record, reboot between OSes and verify that each heartbeat reports the currently running OS. Test Ethernet/LAN reachability from a lab PC, firewall rules, service startup after reboot, token revocation, and recovery after network/server outages. Mocks alone do not prove OS compatibility.
