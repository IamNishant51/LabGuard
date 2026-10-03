# Python monitoring agent

## Purpose and data
A read-only process that collects approved metrics from its own host and sends them to LabGuard. Collect hostname, OS/platform, agent version, CPU, memory, approved local-volume capacity/usage, and heartbeat. Do not collect process names/commands, logged-in usernames, file contents, browsing, screenshots, keystrokes, webcam, or microphone data.

## Configuration (M5, implemented in `agent/`)

| Variable | Required | Default | Rule |
|---|---|---|---|
| `LABGUARD_API_BASE_URL` | yes | — | `http(s)://host[:port]`, no embedded credentials; trailing `/` stripped |
| `LABGUARD_AGENT_TOKEN` | yes | — | Non-blank device bearer token; never logged or printed |
| `LABGUARD_INTERVAL_SECONDS` | no | `30` | Number, 10–3600 (10 s floor enforced) |
| `LABGUARD_REQUEST_TIMEOUT_SECONDS` | no | `10` | Number, 1–300 s, applied to connect/read/write/pool |
| `LABGUARD_LOG_LEVEL` | no | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL`; unknown falls back to `INFO` |

Validate settings at startup. Never commit real settings or print token values. In production, use OS-protected storage or administrator-controlled configuration with restrictive permissions where feasible.

> No `LABGUARD_DEVICE_ID` exists. The M4 server derives device identity from
> the bearer credential (`POST /api/v1/agent/heartbeat` ignores body identity
> fields), so configuring a device ID is unnecessary and unsupported. This
> supersedes the pre-M4 draft that listed a device-ID variable.

## Running (M5)

Foreground only — no service installation or background persistence in this
milestone:

```powershell
cd agent
.venv/Scripts/python -m pip install -e .[dev]
$env:LABGUARD_API_BASE_URL = "http://<lan-server>:8000"
$env:LABGUARD_AGENT_TOKEN = "<enrollment-token-shown-once>"
.venv/Scripts/python -m labguard_agent
```

(Ubuntu: use `.venv/bin/python` and `export`.) Startup prints the destination,
cadence, and timeout — never the token. Stop with Ctrl+C; the loop finishes
no new cycle, closes the HTTP client, and exits 0. Exit code 2 means invalid
configuration (see the stderr message).

Provision the token first via the M4 workflow: a lab manager calls
`POST /api/v1/devices/{id}/enrollment-token` and hands the raw token to the
lab administrator once. Required outbound access: the agent initiates
outbound HTTPS (or HTTP on an isolated LAN) to the API host/port only.

## Troubleshooting (M5)

- `configuration error: LABGUARD_AGENT_TOKEN is required` — token missing/blank.
- `configuration error: ... must start with http:// or https://` — bad base URL.
- `Server rejected the device credential (HTTP 401/403)` — token revoked,
  device deactivated, or wrong token; re-issue via enrollment-token.
- Repeated `heartbeat failed ... retrying` then `after 4 attempts` — network or
  server down; the sample is dropped (no local queue) and the next cycle runs
  on schedule.
- `heartbeat skipped: ...` — a sensor read failed or a volume set was
  unusable; inaccessible volumes are omitted, never zero-filled.
- `422` from the server is not retried — it means the payload failed
  validation; report it as an agent/server version mismatch.

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
