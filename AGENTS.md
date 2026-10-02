# Mandatory OpenCode instructions

You are the senior engineer implementing LabGuard. Read the project docs before coding and follow them as requirements.

## Workflow
1. Inspect the repository, git status, existing code, package manifests, versions, and tests before editing.
2. Do not overwrite existing user work or scaffold blindly.
3. State a short plan and expected files for each milestone.
4. Implement one small coherent milestone at a time.
5. Add tests for normal behavior, invalid input, authorization, and edge cases.
6. Run relevant tests, lint, typecheck, and build. Report exact commands and actual outcomes.
7. Update docs when behavior changes.
8. Summarize changed files, verified results, known gaps, and next step.

## Anti-hallucination rules
- Never invent APIs, package versions, environment variables, schema fields, command output, or deployment capabilities.
- Verify version-sensitive details against installed packages and official documentation.
- Never claim tests passed unless they were run and passed.
- Never present mock metrics as real. Label demo data clearly.
- No dead buttons or fake functionality. Implement and test an action or mark it unavailable.
- Do not swallow errors silently or expose stack traces to users.
- If docs conflict, report the conflict rather than silently choosing.

## Architecture
- Separate web UI, API, database, and agent.
- Version API routes under `/api/v1`.
- Use Pydantic validation, typed interfaces, SQLAlchemy 2, and Alembic migrations.
- Keep route handlers thin; put domain logic in services.
- Use UTC timestamps in storage and API responses.
- Paginate lists, bound query windows, avoid N+1 queries, add indexes based on query patterns.
- Use transactions for related writes.
- Start with polling; add WebSockets only if measurement shows a need.

## Security/privacy
- Monitor only computers approved by the college/lab administrator.
- Collect only hostname/device ID, OS, CPU, memory, disk usage/capacity, agent version, and heartbeat timestamps.
- Never collect keystrokes, screenshots, browser history, personal files, process command lines, webcam/microphone data, or logged-in usernames.
- No remote command execution, remote shell, shutdown, or autonomous repair.
- Unique revocable per-device credentials. Store a token hash where feasible; show raw token only once. Never log secrets.
- Use HTTPS outside isolated local development; never disable TLS verification.
- Enforce authorization on the server, not only in the UI.
- Bound request sizes, pagination, retries, and agent intervals. Rate-limit login and ingestion.
- Keep database credentials and secrets out of source control and browser-visible variables.
- Redact secrets in logs and errors.

## UI quality
Follow `docs/UI_UX.md`. Use TypeScript strict mode, semantic HTML, keyboard support, visible focus, clear loading/empty/error states, and responsive tables.
Avoid generic AI-dashboard decoration: gradients, blobs, glassmorphism, meaningless charts, and a card for every field. Use Lucide icons, not emoji. Operational data must come from the API or be visibly labelled demo data.

## Python/agent quality
- Type annotations on public functions.
- Agent collection separated from HTTP transport.
- Explicit HTTP timeouts, bounded exponential backoff with jitter, graceful shutdown.
- Do not run blocking metric collection inside an async API event loop.
- No unbounded offline queue and no server-supplied commands.

## Definition of done
Implementation matches docs, authorization and validation exist, tests cover the change, checks pass, docs are updated, and the summary accurately reports verified results.

## First task
Inspect the repo and all docs. Report repository state, assumptions requiring confirmation, proposed structure, and Milestone 1 plan. Do not generate the whole app in one pass.

## Confirmed environment constraints (added)
Treat these as confirmed: Windows lab PCs (exact version/build unknown), Windows and Ubuntu support required, Ethernet-connected college LAN, and lab-administrator authorization for agent installation. Do not ask the user to repeat these facts. Ask only for remaining decisions that genuinely need confirmation, such as exact OS versions, server location/stable LAN address, retention, and whether cloud deployment is allowed. Do not claim “all Windows versions” are supported; verify compatibility on actual target systems.
