"""Normalize collected metrics into the exact M4 heartbeat schema (M5).

The M4 implementation (``services/api/.../schemas.py``) is authoritative:
top-level ``platform``/``agent_version``/``agent_timestamp`` plus a
``metrics`` object with required ``cpu_percent``/``memory_percent``,
optional byte counts and top-level disk fields, and at most 32 ``volumes``
each with ``label``/``disk_percent``/``used_bytes``/``total_bytes``.
``hostname`` is accepted by the server but ignored, so it is never sent.

This module builds plain JSON-serializable dicts with exactly those keys —
no extra fields, no credential material.
"""

from __future__ import annotations

from datetime import datetime

from labguard_agent.collect import MAX_TEXT_LEN, MAX_VOLUMES, MetricSample


def _short_text(value: str | None) -> str | None:
    """Mirror the server's strip/non-blank/<=32 rule; unusable becomes None."""
    if value is None:
        return None
    text = value.strip()
    if not text or len(text) > MAX_TEXT_LEN:
        return None
    return text


def build_heartbeat_payload(
    *,
    platform: str | None,
    agent_version: str,
    agent_timestamp: datetime,
    sample: MetricSample,
) -> dict:
    """Return the exact JSON body for ``POST /api/v1/agent/heartbeat``."""
    volumes = [
        {
            "label": volume.label,
            "disk_percent": volume.disk_percent,
            "used_bytes": volume.used_bytes,
            "total_bytes": volume.total_bytes,
        }
        for volume in sample.volumes[:MAX_VOLUMES]
    ]
    return {
        "platform": _short_text(platform),
        "agent_version": _short_text(agent_version),
        "agent_timestamp": agent_timestamp.isoformat(),
        "metrics": {
            "cpu_percent": sample.cpu_percent,
            "memory_percent": sample.memory_percent,
            "memory_used_bytes": sample.memory_used_bytes,
            "memory_total_bytes": sample.memory_total_bytes,
            "disk_percent": None,
            "disk_used_bytes": None,
            "disk_total_bytes": None,
            "volumes": volumes,
        },
    }
