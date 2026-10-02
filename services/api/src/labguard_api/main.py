"""LabGuard central API.

M1 scaffold: health endpoint only. No auth, no telemetry, no schema.
"""

from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="LabGuard API", version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns server time (UTC); never secrets or credentials."""
    return {
        "status": "ok",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "version": app.version,
    }
