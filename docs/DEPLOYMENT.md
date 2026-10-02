# Deployment and operations

## Environments
Keep local development, demo, and pilot/production credentials and databases separate.

## Environment settings
Implementation must define exact names and validate them. Expected categories: database URL, app environment, CORS origins, auth/session secret, log level, heartbeat interval, online/offline thresholds. Never put database credentials or privileged secrets in `NEXT_PUBLIC_*` variables or the agent executable.

## Local development
1. Install supported Node and Python versions.
2. Start PostgreSQL (Docker Compose or local install).
3. Create Python virtual environment and install locked dependencies.
4. Run Alembic migrations.
5. Start FastAPI in development mode.
6. Install web dependencies and start Next.js.
7. Create first admin with a documented safe bootstrap command.
8. Register test device, run agent, verify telemetry.
9. Run tests, lint, typecheck, and build.

Protect or disable interactive API docs in production as appropriate.

## College LAN
- Obtain permission and identify a server owner.
- Assign stable internal DNS/IP.
- Allow only necessary ports through host/network firewall.
- Keep PostgreSQL private; do not expose it to lab clients.
- Use HTTPS with a certificate trusted by clients where feasible.
- HTTP is acceptable only for isolated local development; document that it is unencrypted and never reuse production secrets.
- Configure process supervision, restart policy, backups, log rotation, upgrades, and rollback.
- Agents initiate outbound requests; do not open inbound ports on each PC.

## Cloud
- Web may use a frontend hosting platform.
- API needs a host suitable for a persistent Python API and any required worker.
- Use managed PostgreSQL, backups, TLS, environment secrets, and private networking where supported.
- Restrict CORS to the real frontend origin.
- Confirm college policy permits telemetry leaving the LAN.
- Do not assume a serverless function is suitable for a permanent scheduler.

## Install/uninstall
Install only approved registered devices; issue unique credentials; configure endpoint/ID/token/interval; install service/task only with administrator approval; verify heartbeat.
To remove: stop/uninstall service/task, remove local config according to OS policy, revoke credential, verify authentication fails, record removal if required.

## Operations
Monitor API health and disk use; back up and test restore; patch dependencies; revoke compromised tokens; review audit events; ensure time sync; review retention and maintain rollback plan.

## College LAN deployment (added)
The lab administrator is expected to authorize installation. Confirm the server owner and college IT/network rules. Prefer a central API and database on an approved, always-on internal server or designated lab machine. Assign a stable internal DNS/IP and configure agents to use it. Permit only the required outbound connection from lab PCs to the API. Keep PostgreSQL private. Use HTTPS with a certificate trusted by clients where practical; never disable certificate validation to bypass errors. Test connectivity from an actual lab PC.

## Windows, Ubuntu, and dual boot (added)
Test installation and startup on the actual Windows and Ubuntu versions present in the lab. On Windows, document whether the agent runs as a service or scheduled task, required privileges, logs, upgrades, and removal. On Ubuntu, prefer a dedicated least-privilege service account and a documented systemd unit after validating the target release. For dual boot, install separately in both OS installations; only the currently booted OS reports. Uninstall by stopping/removing the service or task, removing local configuration according to policy, revoking the credential, and verifying that the revoked credential is rejected.
