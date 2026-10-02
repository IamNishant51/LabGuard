# API contract v1

All routes are under `/api/v1`. If implementation changes a route or payload, update this document and tests together.

## Agent
### `POST /api/v1/agent/heartbeat`
Auth: unique per-device bearer token. Device identity comes from the credential association, never from a trusted body field.

Example:
```json
{
  "agent_version": "0.1.0",
  "platform": "Windows",
  "hostname": "LAB-PC-023",
  "metrics": {
    "cpu_percent": 24.8,
    "memory_percent": 68.2,
    "memory_used_bytes": 7300000000,
    "memory_total_bytes": 16000000000,
    "volumes": [
      {"label": "C:", "disk_percent": 71.4, "used_bytes": 250000000000, "total_bytes": 350000000000}
    ]
  }
}
```
Server sets `recorded_at` and `last_seen_at`. Validate bounds and request size. Return `{ "accepted": true, "server_time": "..." }`. Expected statuses: 200 accepted, 401 invalid/revoked token, 422 invalid payload, 429 rate-limited, 5xx transient failure.

## Auth
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
Prefer secure HttpOnly SameSite cookies for browser sessions; implement CSRF protection where required. Do not store long-lived privileged tokens in localStorage by default.

## Admin
- `GET/POST /api/v1/labs`
- `PATCH /api/v1/labs/{lab_id}`
- `GET/POST /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `PATCH /api/v1/devices/{device_id}`
- `POST /api/v1/devices/{device_id}/enrollment-token`
- `POST /api/v1/devices/{device_id}/revoke-agent`

Raw enrollment token is returned once only.

## Dashboard and maintenance
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/devices/{device_id}/metrics?from=...&to=...&limit=...`
- `GET /api/v1/alerts?status=open&lab_id=...&page=...`
- `POST /api/v1/alerts/{alert_id}/acknowledge`
- `POST /api/v1/alerts/{alert_id}/resolve`
- `GET /api/v1/incidents?status=...&page=...`
- `POST /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `PATCH /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/{incident_id}/resolve`
- `GET /api/v1/reports/incidents.csv`

## Pagination
Use `{ "items": [], "page": 1, "page_size": 25, "total": 0 }`. Bound page size (e.g. 1–100); use allow-listed sort fields and stable sorting.

## Errors
Use `{ "error": { "code": "DEVICE_NOT_FOUND", "message": "The requested device was not found." } }`. Never expose stack traces, SQL, filesystem paths, internal hostnames, or secrets.

## Authorization
Admin: all authorized resources and user/device administration.
Staff: view authorized labs, manage alerts/incidents there.
Viewer: read-only authorized labs.
Enforce server-side, including cross-lab access checks.
