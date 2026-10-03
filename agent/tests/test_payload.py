"""Payload tests: exact M4 key shape, units, limits, and schema compatibility."""

from datetime import datetime, timezone

from labguard_agent.collect import MetricSample, VolumeSample
from labguard_agent.payload import build_heartbeat_payload


def _sample(**overrides: object) -> MetricSample:
    base: dict = {
        "cpu_percent": 24.8,
        "memory_percent": 68.2,
        "memory_used_bytes": 7300000000,
        "memory_total_bytes": 16000000000,
        "volumes": (
            VolumeSample(
                label="C:", disk_percent=71.4, used_bytes=250000000000,
                total_bytes=350000000000,
            ),
        ),
    }
    base.update(overrides)
    return MetricSample(**base)


def test_exact_top_level_and_metrics_keys() -> None:
    payload = build_heartbeat_payload(
        platform="Windows",
        agent_version="0.1.0",
        agent_timestamp=datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc),
        sample=_sample(),
    )
    assert set(payload) == {"platform", "agent_version", "agent_timestamp", "metrics"}
    assert set(payload["metrics"]) == {
        "cpu_percent",
        "memory_percent",
        "memory_used_bytes",
        "memory_total_bytes",
        "disk_percent",
        "disk_used_bytes",
        "disk_total_bytes",
        "volumes",
    }
    # No hostname: the server ignores body identity; it is never sent.
    assert "hostname" not in payload
    assert payload["agent_timestamp"] == "2026-10-03T12:00:00+00:00"


def test_volume_entry_exact_keys_and_units() -> None:
    payload = build_heartbeat_payload(
        platform="Linux",
        agent_version="0.1.0",
        agent_timestamp=datetime.now(timezone.utc),
        sample=_sample(),
    )
    (volume,) = payload["metrics"]["volumes"]
    assert set(volume) == {"label", "disk_percent", "used_bytes", "total_bytes"}
    assert volume == {
        "label": "C:",
        "disk_percent": 71.4,
        "used_bytes": 250000000000,
        "total_bytes": 350000000000,
    }


def test_volumes_capped_at_32() -> None:
    many = tuple(
        VolumeSample(label=f"V{i}", disk_percent=1.0, used_bytes=1, total_bytes=2)
        for i in range(40)
    )
    payload = build_heartbeat_payload(
        platform="Linux",
        agent_version="0.1.0",
        agent_timestamp=datetime.now(timezone.utc),
        sample=_sample(volumes=many),
    )
    assert len(payload["metrics"]["volumes"]) == 32


def _build(platform: str | None, version: str) -> dict:
    return build_heartbeat_payload(
        platform=platform,
        agent_version=version,
        agent_timestamp=datetime.now(timezone.utc),
        sample=_sample(),
    )


def test_blank_or_oversize_platform_and_version_become_null() -> None:
    assert _build("   ", "0.1.0")["platform"] is None
    assert _build("X" * 33, "0.1.0")["platform"] is None
    assert _build(None, "0.1.0")["platform"] is None
    assert _build("Windows", "")["agent_version"] is None
    assert _build("Windows", "0.1.0")["platform"] == "Windows"


def test_missing_optionals_stay_null_not_zero() -> None:
    payload = build_heartbeat_payload(
        platform=None,
        agent_version="0.1.0",
        agent_timestamp=datetime.now(timezone.utc),
        sample=_sample(memory_used_bytes=None, memory_total_bytes=None, volumes=()),
    )
    metrics = payload["metrics"]
    assert metrics["memory_used_bytes"] is None
    assert metrics["memory_total_bytes"] is None
    assert metrics["volumes"] == []
    assert metrics["disk_percent"] is None


def test_m4_schema_constraints_mirrored() -> None:
    """Guard the contract: every value must satisfy the M4 field rules."""
    payload = build_heartbeat_payload(
        platform="Windows",
        agent_version="0.1.0",
        agent_timestamp=datetime.now(timezone.utc),
        sample=_sample(),
    )
    metrics = payload["metrics"]
    assert 0.0 <= metrics["cpu_percent"] <= 100.0
    assert 0.0 <= metrics["memory_percent"] <= 100.0
    for key in ("memory_used_bytes", "memory_total_bytes"):
        assert metrics[key] is None or metrics[key] >= 0
    assert len(metrics["volumes"]) <= 32
    for volume in metrics["volumes"]:
        assert 1 <= len(volume["label"]) <= 64
        assert 0.0 <= volume["disk_percent"] <= 100.0
        assert volume["used_bytes"] >= 0
        assert volume["total_bytes"] >= 0
