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
