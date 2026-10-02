# Architecture

## Data flow
1. Admin creates lab and device.
2. Server issues a one-time enrollment token and stores its hash.
3. Agent is configured with API URL, device ID, and token.
4. Agent collects approved metrics and initiates an outbound HTTP request.
5. FastAPI authenticates the token, resolves its device association, validates payload, and writes telemetry/last-seen in a transaction.
6. API evaluates thresholds and deduplicates alerts.
7. Next.js dashboard polls the API and displays persisted data.
8. Staff manage alerts/incidents; server checks permissions and writes audit events.

## Topology
`Lab PC + Python agent -> HTTPS/LAN -> FastAPI -> PostgreSQL -> Next.js dashboard`

Agent initiates outbound requests; the server does not need an inbound listener on every PC.

## Suggested repository structure
```text
labguard/
  AGENTS.md
  README.md
  .env.example
  docs/
  apps/web/                  # Next.js
  services/api/               # FastAPI
  agent/
    pyproject.toml
    src/labguard_agent/
    tests/
  infra/
  .github/workflows/
```
Treat this as a proposal. Inspect existing code before restructuring.

## Boundaries
- Web: presentation, forms, user session, API calls.
- API: authentication, authorization, validation, business logic.
- DB: durable records and constraints.
- Agent: read-only local metric collection and outbound telemetry.
- Scheduler: one documented mechanism for stale-device checks/retention. Avoid duplicate schedulers.

## Status
Use server time and `last_seen_at`:
- `never_seen`: no valid heartbeat.
- `online`: age within online threshold.
- `stale`: beyond online threshold but within offline threshold.
- `offline`: beyond offline threshold.
Thresholds are configuration and tested at exact boundaries. UI may use “Delayed” and “Not reporting” to avoid claiming an exact cause.

## Performance
Index device/lab/status lookups, `(device_id, recorded_at DESC)`, and alert/incident status plus created time as needed. Paginate lists and bound chart time ranges. Start dashboard polling at 15–30 seconds and tune with tests. For 60 PCs reporting every 30 seconds, expect about 172,800 reports/day; define retention/downsampling before scaling. Do not add Redis/Kafka/Kubernetes without measured need.

## Deployment modes
- **Primary recommendation: college LAN.** Run the API and database on an approved, always-on college server or designated lab machine with a stable internal IP/DNS name. Ethernet-connected PCs send outbound requests to it. Internet access is not required for telemetry, but updates and package installation may need internet access or an approved offline process.
- **Cloud (optional):** only if the college approves sending device telemetry outside its network. Use HTTPS and managed secrets/database.

## Windows, Ubuntu, and dual boot
- Share one cross-platform agent codebase. Use platform-aware metric collection and disk-volume enumeration; do not assume a Windows drive letter or Linux mount path.
- Initial tested targets: Windows 10/11 x64 and supported Ubuntu LTS x64. Exact versions must be recorded and verified in the pilot. Older Windows releases are not promised until tested.
- On a dual-boot PC, install and configure the agent separately in each OS. Only the currently running OS reports. If both installations use credentials associated with the same registered physical-computer record, each heartbeat should update the reported platform/agent version; the OSes cannot report simultaneously on a normal dual-boot setup. Document this behavior in the UI and runbook.
- Avoid OS-specific code outside a small platform adapter. Test the agent on real Windows and Ubuntu machines; mocks alone do not establish OS compatibility.

## Cross-platform and LAN deployment requirements (added)
The primary deployment is an approved, always-on internal server or designated lab machine running the API and database. Give it a stable internal IP/DNS name. Ethernet-connected PCs initiate outbound requests to the API. Keep PostgreSQL inaccessible to lab PCs. Internet access should not be required for normal telemetry after dependencies are installed.

Maintain one cross-platform agent codebase with platform-aware metric collection and disk-volume enumeration. Initial targets are Windows 10/11 x64 and supported Ubuntu LTS x64; verify actual versions during the pilot. Older Windows releases are not guaranteed until tested.

For a dual-boot PC, install/configure the agent separately in Windows and Ubuntu. Only the currently booted OS reports. If both installations use credentials for one registered physical-computer record, each heartbeat updates the active platform and agent version. Alternatively, use clearly labelled separate records for each OS installation. Choose one model before pilot enrollment. Test on real Windows and Ubuntu machines; mocks alone do not prove compatibility.
