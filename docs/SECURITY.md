# Security, privacy, and threat model

## Goal
Only authorized agents submit metrics for their own devices; only authorized staff access or modify records. LabGuard is not a remote-control or surveillance system.

## Main risks and controls
- **Stolen token:** high-entropy unique per-device token, hash at rest, TLS, revocation, no token logs, rotation procedure.
- **Spoofed device:** bind token to device server-side; ignore body-supplied identity for authorization.
- **Unauthorized staff:** server-side RBAC and lab scoping; tests for cross-lab access.
- **Malformed/hostile requests:** Pydantic validation, body limits, rate limits, timeouts, safe errors.
- **Database exposure:** least privilege, private network, secrets outside source control, backups.
- **Browser attacks:** safe rendering, secure cookies, CSRF protection when needed, strict CORS and security headers.
- **Log leaks:** redact authorization headers and secrets.
- **Denial of service:** bounded request size, pagination, indexes, agent interval floor.

## Privacy
Get approval before installation. Publish the metric inventory and purpose. Collect minimum necessary data. Restrict access. Define retention. Keep audit records for administrative changes. Document uninstall and credential revocation.

## Device credentials (M4, implemented)
- **Independent of human sessions:** agents authenticate with a per-device bearer token (`Authorization: Bearer <token>` on `POST /api/v1/agent/heartbeat`); no user session or cookie is accepted or required there. Human endpoints are unchanged.
- **Generation and storage:** each enrollment token is a high-entropy 256-bit opaque value (`security.new_device_token`); only its SHA-256 hex digest is stored (`agent_credentials.token_hash`, unique). The raw token is returned exactly once in the issuance response and is never stored, logged, audited, or returned again.
- **Lifecycle:** credentials are reusable until revoked — not single-use. `expires_at` is reserved and currently always NULL, so no expiry is enforced; revocation is the lifecycle mechanism. Several active credentials may exist per device; `POST /api/v1/devices/{id}/revoke-agent` (lab managers only) revokes all of them at once and is idempotent when nothing is active. Rotation is revoke-then-issue. On a hash collision the server reports `503 TOKEN_COLLISION`; the client retries issuance.
- **Authentication failures are uniform:** missing, unknown, revoked, or expired tokens — and credentials bound to deactivated devices or inactive labs — all return the same `401 UNAUTHENTICATED` (`Invalid or revoked device credential.`), so no state can be probed.
- **Identity binding:** heartbeat device identity comes from the credential association server-side; body-supplied identity fields are accepted but ignored and can never redirect a heartbeat to another device.
- **Audit:** enrollment and revocation write `device.enrollment_issued` / `device.credential_revoked` rows (metadata: `hostname`, `lab_id`, `credential_id` only — never raw tokens). Heartbeats write no audit rows.
- **Deferred:** heartbeat rate limiting is deferred to M9; heartbeat payload size is bounded by schema (required percentages, byte counts, max 32 volumes, length limits).

## Production checklist
- [ ] HTTPS and valid certificate.
- [ ] Secrets outside source control.
- [ ] Unique revocable agent credentials.
- [ ] Password hashing or trusted identity provider.
- [ ] RBAC and lab-scope tests.
- [ ] Login/ingestion rate limits.
- [ ] Restricted CORS.
- [ ] Database not public.
- [ ] Backup and restore test.
- [ ] Dependency audit and lockfiles.
- [ ] Safe logs.
- [ ] Install/uninstall and retention procedure.

## Credential incident
Revoke leaked token, issue replacement, inspect audit logs, and remove leaked secret from repository history where appropriate. Deleting it from the latest file alone does not make it safe.
