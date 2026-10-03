"""Agent heartbeat endpoint (M4): authenticated telemetry ingestion.

Authentication is per-device bearer token only — no human session, no
cookies. Device identity comes from the credential association; body
identity fields are ignored. Each accepted heartbeat writes one metric
row (plus volume rows), stamps ``last_seen_at``/``last_used_at`` from
the server clock, and refreshes the reported platform/agent version, all
in a single transaction. Heartbeats write no audit rows.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from labguard_api.database import get_db
from labguard_api.deps import CurrentDevice
from labguard_api.models import Metric, MetricVolume
from labguard_api.schemas import HeartbeatIn, HeartbeatOut

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/heartbeat", response_model=HeartbeatOut)
def heartbeat(
    payload: HeartbeatIn,
    device_auth: CurrentDevice,
    db: Session = Depends(get_db),
) -> HeartbeatOut:
    device, credential = device_auth
    now = datetime.now(timezone.utc)
    metrics = payload.metrics
    row = Metric(
        device_id=device.id,
        recorded_at=now,
        agent_timestamp=payload.agent_timestamp,
        cpu_percent=metrics.cpu_percent,
        memory_percent=metrics.memory_percent,
        memory_used_bytes=metrics.memory_used_bytes,
        memory_total_bytes=metrics.memory_total_bytes,
        disk_percent=metrics.disk_percent,
        disk_used_bytes=metrics.disk_used_bytes,
        disk_total_bytes=metrics.disk_total_bytes,
    )
    db.add(row)
    db.flush()
    for volume in metrics.volumes:
        db.add(
            MetricVolume(
                metric_id=row.id,
                label=volume.label,
                disk_percent=volume.disk_percent,
                used_bytes=volume.used_bytes,
                total_bytes=volume.total_bytes,
            )
        )
    # Dual-boot note: each heartbeat reports the currently running OS, so
    # the stored platform/agent version tracks the latest reporter.
    if payload.platform is not None:
        device.platform = payload.platform
    if payload.agent_version is not None:
        device.agent_version = payload.agent_version
    device.last_seen_at = now
    credential.last_used_at = now
    db.flush()
    return HeartbeatOut(accepted=True, server_time=now)
