# API contract v1

All routes are under `/api/v1`. If implementation changes a route or payload, update this document and tests together.

Sections marked **Implemented (M2)** match the code and tests. Sections marked **Planned** are forward-looking and not implemented yet.

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

## Admin — Planned (only `GET/POST /api/v1/labs` is implemented in M2)
- `GET/POST /api/v1/labs`
- `PATCH /api/v1/labs/{lab_id}`
- `GET/POST /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `PATCH /api/v1/devices/{device_id}`
- `POST /api/v1/devices/{device_id}/enrollment-token`
- `POST /api/v1/devices/{device_id}/revoke-agent`

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
Implemented (M2) error codes: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `LAB_NOT_FOUND` (404), `USER_NOT_FOUND` (404), `BOOTSTRAP_CLOSED` (403), `LAB_EXISTS` (409), `RATE_LIMITED` (429). FastAPI request-validation failures return `422`.

## Authorization
Admin: all authorized resources and user/device administration.
Staff: view authorized labs, manage alerts/incidents there.
Viewer: read-only authorized labs.
Enforce server-side, including cross-lab access checks.
M2 implements the lab half of this: global admins see all active labs, other users only labs they belong to, lab management requires the lab `admin` role, and anything the caller may not see is 404 (see Labs above). Device administration, alerts, and incidents are planned.
