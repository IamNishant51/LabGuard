# Python monitoring agent

## Purpose and data
A read-only process that collects approved metrics from its own host and sends them to LabGuard. Collect hostname, OS/platform, agent version, CPU, memory, approved local-volume capacity/usage, and heartbeat. Do not collect process names/commands, logged-in usernames, file contents, browsing, screenshots, keystrokes, webcam, or microphone data.

## Configuration
- `LABGUARD_API_BASE_URL`
- `LABGUARD_DEVICE_ID`
- `LABGUARD_AGENT_TOKEN`
- `LABGUARD_INTERVAL_SECONDS`
- `LABGUARD_REQUEST_TIMEOUT_SECONDS`
- optional `LABGUARD_LOG_LEVEL`

Validate settings at startup. Never commit real settings or print token values. In production, use OS-protected storage or administrator-controlled configuration with restrictive permissions where feasible.

## Collection
Use `psutil`. Separate collection from HTTP transport. Enumerate suitable local volumes in a platform-aware way; never assume `C:\` exists. Inaccessible volumes should be omitted with a safe diagnostic, not reported as zero. Do not fabricate values.

## Delivery
Use `httpx` or a selected maintained client. Set connect/read/overall timeouts. Use HTTPS in production. Retry transient network errors, 429, and 5xx with bounded exponential backoff and jitter; respect `Retry-After` when available. On 401/403, stop rapid retries and report an actionable credential error. Prevent overlapping sends. Do not create an unbounded offline queue; MVP may discard failed samples after logging.

## Lifecycle and packaging
Support graceful shutdown. Enforce a sensible minimum interval (suggested 10 seconds unless explicitly configured). Do not create hidden persistence. First run as `python -m labguard_agent`; package for Windows only after tests pass. PyInstaller may be evaluated, but confirm IT/endpoint-protection policy. Never bundle one shared secret into a fleet-wide executable. Document install, service/task setup, revocation, and uninstall.

## Tests
Mock psutil; cover missing/inaccessible disks, success, timeout, DNS/TLS failure, 401/403, 429, 5xx, bounded retry, graceful shutdown, and secret redaction. Confirm no remote command handler exists.

## Cross-platform support (added)
Use one Python codebase for Windows and Ubuntu/Linux. Initial targets are Windows 10/11 x64 and supported Ubuntu LTS x64, subject to pilot verification. Do not claim support for all historical Windows versions. Keep OS-specific behavior behind small adapters and report the active platform on every heartbeat.

For dual boot, install/configure the agent separately in each OS. The agent runs only in the currently booted OS. Windows volume discovery must handle drive letters and inaccessible/removable volumes; Linux discovery must handle mount points and pseudo-filesystems. Never assume `C:\\` or `/` is the only relevant volume. Omit inaccessible or unsupported volumes with a safe diagnostic rather than reporting zero.
