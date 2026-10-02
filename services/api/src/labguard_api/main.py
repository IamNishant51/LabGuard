"""LabGuard central API.

M2: health probe plus auth (bootstrap/login/logout/me) and lab scoping.
Telemetry, enrollment, alerts, and incidents arrive in later milestones.
"""

from datetime import datetime, timezone

from fastapi import FastAPI

from labguard_api.errors import ApiError, api_error_handler
from labguard_api.routers import auth, labs

app = FastAPI(title="LabGuard API", version="0.1.0")
app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
app.include_router(auth.router)
app.include_router(labs.router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns server time (UTC); never secrets or credentials."""
    return {
        "status": "ok",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "version": app.version,
    }
