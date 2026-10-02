# API contract v1

All routes are under `/api/v1`. If implementation changes a route or payload, update this document and tests together.

Sections marked **Implemented (M2)** or **Implemented (M3)** match the code and tests. Sections marked **Planned** are forward-looking and not implemented yet.

## Auth — Implemented (M2)
Session credential: an opaque token issued at login. Browsers receive it in the `labguard_session` cookie (`HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure=False` until TLS lands); API clients send the same value as `Authorization: Bearer <token>`. Cookie takes precedence when both are present.

### `POST /api/v1/auth/bootstrap`
Creates the initial global admin. Works only when no users exist.
Request: `{ "email": "...", "password": "...", "display_name": "..." }` — email is normalized (trimmed, lowercased, must match `user@host.tld`); password minimum 12 characters and maximum 72 bytes; display name must be non-blank, max 100 chars.
Responses: `201` with the user object (role forced to `admin`); `403` `BOOTSTRAP_CLOSED` once any user exists; `422` for invalid input. On PostgreSQL concurrent bootstraps are serialized by a transaction-scoped advisory lock so exactly one wins.

### `POST /api/v1/auth/login`
Request: `{ "email": "...", "password": "..." }` (email normalized as above).
Responses: `200` with the user object plus `Set-Cookie: labguard_session=...`; `401` `UNAUTHENTICATED` for unknown user, wrong password, or inactive account (identical response); `429` `RATE_LIMITED` after more than 20 attempts per 60 seconds from one client IP (every login POST counts, success or failure; buckets are per-process, in-memory); `422` for invalid input.

### `POST /api/v1/auth/logout`
Requires authentication. Sets `revoked_at` on the current session, clears the cookie. Response: `204` (no body); `401` without a valid session.

### `GET /api/v1/auth/me`
Requires authentication. Response: `200` with the user object; `401` `UNAUTHENTICATED` for missing, unknown, expired, revoked, or inactive-account sessions.

User object shape: `{ "id": "<uuid>", "email": "...", "display_name": "...", "role": "admin|staff|viewer", "is_active": true }`. Password hashes and session tokens are never serialized.

## Labs — Implemented (M2)
Lab object shape: `{ "id": "<uuid>", "name": "...", "location": "...|null", "is_active": true, "created_at": "<utc-iso>" }`.

### `POST /api/v1/labs`
Global admin only. Request: `{ "name": "...", "location": "...|null" }` (name stripped, non-blank, max 100; location max 200).
Responses: `201` with the lab; `401` unauthenticated; `403` for non-admins; `409` `LAB_EXISTS` on duplicate name; `422` for invalid input.

### `GET /api/v1/labs`
Requires authentication. Global admins see all active labs; other users see only active labs they belong to, ordered by name. Query: `page` (default 1, min 1), `page_size` (default 25, 1–100). Response: `200` `{ "items": [...], "page": 1, "page_size": 25, "total": 0 }`; out-of-range pages clamp to the last page. `401` unauthenticated; `422` for out-of-range paging.

### `GET /api/v1/labs/{lab_id}`
Requires authentication. Global admins may read any active lab; other users only labs they belong to. Responses: `200` with the lab; `404` `LAB_NOT_FOUND` for missing/inactive labs and for labs the caller may not see; `401` unauthenticated; `422` for a non-UUID id.

### `POST /api/v1/labs/{lab_id}/members`
Lab managers only (global admins, or members holding the lab `admin` role). Request: `{ "user_id": "<uuid>", "role": "admin|staff|viewer" }` (default `viewer`). Creates the membership or updates the role of an existing one.
Responses: `201` `{ "user_id": "<uuid>", "email": "...", "display_name": "...", "role": "..." }`; `404` `LAB_NOT_FOUND` for missing/inactive labs, callers without membership, or missing membership on delete; `404` `USER_NOT_FOUND` for missing/inactive users; `403` for members without the manager role; `401` unauthenticated; `422` for invalid input.

### `DELETE /api/v1/labs/{lab_id}/members/{user_id}`
Lab managers only. Responses: `204` (no body); same 401/403/404 rules as above.

## Devices — Implemented (M3)
Device object shape: `{ "id": "<uuid>", "lab_id": "<uuid>", "hostname": "...", "display_name": "...|null", "platform": "...|null", "agent_version": "...|null", "is_active": true, "last_seen_at": null, "created_at": "<utc-iso>", "updated_at": "<utc-iso>" }`. `last_seen_at` is always null in M3 — nothing writes it until the M4 heartbeat lands.

Device identity is the (`lab_id`, `hostname`) pair. Hostnames are normalized on input (trimmed, lowercased) and must be non-blank, max 255 chars, and match `[a-z0-9][a-z0-9._-]*` (letters, digits, dots, underscores, hyphens); the same hostname may exist in different labs. Identity fields are immutable: `PATCH` accepts only `display_name` (max 255), `platform` (max 32), `agent_version` (max 32), and `is_active`; unknown fields such as `hostname` or `lab_id` are ignored, never applied. There are no device credentials, enrollment tokens, or per-device secrets anywhere in M3.

Reads follow lab visibility: global admins may read devices in any active lab; other users only devices in active labs they belong to (any membership role, including viewer). Deactivated devices stay visible to authorized callers — deactivation is the delete path and managers need the record to re-enable it. Anything the caller may not see reads as the device missing, never as a lab problem, so device IDs cannot probe lab membership. Writes require lab managers (global admins, or members holding the lab `admin` role).

### `POST /api/v1/devices`
Lab managers only. Request: `{ "lab_id": "<uuid>", "hostname": "...", "display_name": "...|null", "platform": "...|null", "agent_version": "...|null" }`.
Responses: `201` with the device (hostname stored normalized); `401` unauthenticated; `404` `LAB_NOT_FOUND` for a missing/inactive lab and for labs the caller does not manage (members without the manager role get `403`, not 404); `409` `DEVICE_EXISTS` when the (`lab_id`, `hostname`) identity already exists, including when a concurrent registration wins the race; `422` for invalid input. Writes a `device.registered` audit row in the same transaction.

### `GET /api/v1/devices`
Requires authentication. Lists devices in active labs the caller may see, ordered by hostname then id. Query: `lab_id` (optional UUID filter — a value pointing at an invisible lab returns `404` `LAB_NOT_FOUND`, never an empty list), `q` (optional, max 100 chars; case-insensitive substring match on hostname only, blank means no filtering), `is_active` (optional boolean), `page` (default 1, min 1), `page_size` (default 25, 1–100). Response: `200` `{ "items": [...], "page": 1, "page_size": 25, "total": 0 }`; out-of-range pages clamp to the last page. `401` unauthenticated; `404` for an invisible `lab_id` filter; `422` for out-of-range paging or a non-UUID filter.

### `GET /api/v1/devices/{device_id}`
Requires authentication. Responses: `200` with the device; `404` `DEVICE_NOT_FOUND` for missing devices and for devices the caller may not see (including devices in invisible or inactive labs); `401` unauthenticated; `422` for a non-UUID id.

### `PATCH /api/v1/devices/{device_id}`
Lab managers only (global admin, or the lab `admin` role on the device's lab). Request: any subset of `{ "display_name", "platform", "agent_version", "is_active" }` — an empty patch succeeds as a no-op without writing an audit row. Only fields whose value actually changes are recorded.
Responses: `200` with the updated device; `401` unauthenticated; `403` for lab members without the manager role; `404` `DEVICE_NOT_FOUND` for missing devices, devices the caller may not see, and devices whose lab the caller does not manage; `422` for invalid input. A metadata change writes `device.updated`; flipping `is_active` writes `device.deactivated` (false) or `device.reactivated` (true) instead. Audit rows are written in the same transaction as the device change, so a failed request leaves neither a partial device nor a stray audit row.

Audit rows are write-only in M3: there is no audit-read endpoint. Each row records the acting user, the action, the device id, and metadata limited to `hostname`, `lab_id`, `is_active`, `changed`, plus the device fields supplied at registration — never credentials, tokens, or secrets.

Device enrollment credentials, per-device bearer tokens, heartbeat, and telemetry remain future work (see Admin — Planned and Agent heartbeat — Planned).

## Agent heartbeat — Planned
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

## Admin — Planned (labs CRUD in M2; device register/list/get/patch in M3)
- `GET/POST /api/v1/labs` — Implemented (M2)
- `PATCH /api/v1/labs/{lab_id}` — Planned
- `GET/POST /api/v1/devices` — Implemented (M3)
- `GET /api/v1/devices/{device_id}` — Implemented (M3)
- `PATCH /api/v1/devices/{device_id}` — Implemented (M3)
- `POST /api/v1/devices/{device_id}/enrollment-token` — Planned (M4)
- `POST /api/v1/devices/{device_id}/revoke-agent` — Planned (M4)

Raw enrollment token is returned once only.

## Dashboard and maintenance — Planned
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
Implemented (M2) error codes: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `LAB_NOT_FOUND` (404), `USER_NOT_FOUND` (404), `BOOTSTRAP_CLOSED` (403), `LAB_EXISTS` (409), `RATE_LIMITED` (429). Implemented (M3) error codes: `DEVICE_NOT_FOUND` (404, also used to mask devices the caller may not see), `DEVICE_EXISTS` (409). FastAPI request-validation failures return `422`.

## Authorization
Admin: all authorized resources and user/device administration.
Staff: view authorized labs, manage alerts/incidents there.
Viewer: read-only authorized labs.
Enforce server-side, including cross-lab access checks.
M2 implements the lab half of this: global admins see all active labs, other users only labs they belong to, lab management requires the lab `admin` role, and anything the caller may not see is 404 (see Labs above). M3 adds device register/list/get/patch under the same model — reads follow lab visibility, writes require lab managers, cross-lab access is 404-masked — but issues no device credentials: enrollment tokens, heartbeat auth, alerts, and incidents are planned.
