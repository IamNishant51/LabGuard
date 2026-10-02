# Product Requirements Document

## Product
LabGuard is a centralized health-monitoring and incident-management tool for authorized college computer labs. A Python agent sends basic metrics to an API; the dashboard displays status, history, alerts, and incidents.

## Roles
- **Admin:** manage labs/devices/users, enroll or revoke agents, configure thresholds, view audit records.
- **Staff:** view permitted labs, inspect metrics/alerts, create and manage incidents.
- **Viewer (optional):** read-only access to authorized labs.
Do not add student-facing accounts to MVP unless the college asks for them.

## User stories and acceptance criteria
### Register device
Admin creates a lab and device with a unique ID. Duplicate IDs are rejected. A device is not online before a valid heartbeat.

### Enroll agent
Admin generates a high-entropy per-device credential. Raw token appears once; only a hash is stored where feasible. Credential is revocable. An agent cannot report for another device.

### Ingest telemetry
Agent submits validated CPU, memory, disk, platform, hostname, and agent version. Server time is authoritative for `last_seen_at`. Invalid values are rejected. Retries do not corrupt device identity. Responses reveal no internal errors.

### Dashboard and device detail
Dashboard shows reporting, delayed, not-reporting devices, open alerts, and incidents. Device list is searchable, filterable, paginated, and role-scoped. Details show recent metrics with bounded history.

### Alerts
Rules cover CPU, memory, disk, and missing heartbeat. Thresholds are configurable. Repeated heartbeats must not create duplicate alerts for the same ongoing condition. Alerts can be acknowledged/resolved and audited.

### Incidents
Staff can create, assign, update, and resolve incidents. Validate state transitions and retain resolution notes/history.

### Reports
Authorized users can filter incidents and export CSV. Escape CSV fields safely, including formula-leading cells.

## MVP
Authentication/RBAC; labs/devices; agent enrollment/revocation; telemetry; online/stale/offline status; device list/detail; charts; alerts; incident lifecycle; basic CSV; audit events; automated tests; deployment instructions.

## Later
Windows service installer, approved bulk deployment, SNMP, email alerts, SSO, advanced retention/downsampling, multi-campus support.

## Non-goals
No remote control, shell, repair, shutdown, surveillance, antivirus replacement, or claims that an offline PC's exact failure cause is known.

## Success criteria for demo
At least two authorized PCs report real metrics; dashboard updates within its polling interval; stopping an agent causes a stale alert; thresholds behave as configured; staff can resolve an incident; authorization tests pass; no secrets appear in logs/repository.

## Confirmed project constraints
- Lab PCs use Windows; exact version/build is not yet known.
- The implementation must support Windows and Ubuntu/Linux, including dual-boot computers.
- Lab PCs are connected by Ethernet. Prefer a central API reachable on the college LAN, so telemetry stays inside the network and internet access is not required for normal operation.
- The lab administrator will authorize agent installation and operation.

## Validate during pilot
Exact Windows editions/builds and architecture; Ubuntu version; Python/runtime compatibility; number of PCs; server host and stable LAN address/DNS; firewall rules; polling interval; staff access; retention policy; whether the college permits cloud hosting. Support Windows 10/11 x64 and supported Ubuntu LTS x64 first. Do not claim compatibility with every old Windows version until tested.

## Confirmed project constraints (added)
- Lab PCs use Windows, but the exact version/build is not yet known.
- LabGuard must support Windows and Ubuntu/Linux, including dual-boot computers.
- PCs connect by Ethernet. Prefer a central API on the college LAN so normal telemetry does not require internet access.
- The lab administrator will authorize installation and operation of monitoring agents.

Before the pilot, record exact Windows edition/version/build and architecture, Ubuntu release, PC count, server owner and stable LAN address/DNS, firewall rules, polling interval, staff access, retention policy, and whether cloud hosting is permitted. Initial targets should be Windows 10/11 x64 and supported Ubuntu LTS x64. Do not claim compatibility with every historical Windows release until tested.
