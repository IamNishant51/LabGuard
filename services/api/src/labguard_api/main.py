"""LabGuard central API.

M4: health probe, auth, lab scoping, device identity/management, per-device
enrollment credentials, and agent heartbeat ingestion. Alerts and incidents
arrive in later milestones.
"""

from datetime import datetime, timezone

from fastapi import FastAPI

from labguard_api.errors import ApiError, api_error_handler
from labguard_api.routers import agent, auth, devices, labs

app = FastAPI(title="LabGuard API", version="0.1.0")
app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
app.include_router(auth.router)
app.include_router(labs.router)
app.include_router(devices.router)
app.include_router(agent.router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns server time (UTC); never secrets or credentials."""
    return {
        "status": "ok",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "version": app.version,
    }
