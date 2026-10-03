"""Approved system-metric collection via psutil (M5).

Collection is deliberately separated from HTTP transport: this module never
touches the network. It collects only the minimum approved inventory — CPU
utilization, memory totals/usage/utilization, accessible local-volume
capacity/usage, and platform identity. It never reads process names or
command lines, logged-in usernames, file contents, browsing activity,
screenshots, keystrokes, clipboard data, or webcam/microphone data.

Inaccessible, transient, or unsupported volumes are omitted (never reported
as zero), and non-finite or out-of-range numbers never become fabricated
values: required measurements raise :class:`CollectionError`, optional ones
become ``None`` or cause the volume to be skipped.
"""

from __future__ import annotations

import logging
import math
import platform as _platform
from dataclasses import dataclass, field

import psutil  # type: ignore[import-untyped]  # psutil ships no stubs; untyped at the boundary only

log = logging.getLogger(__name__)

#: Cap mirroring the M4 schema (``MAX_VOLUMES_PER_HEARTBEAT``).
MAX_VOLUMES = 32
MAX_LABEL_LEN = 64
MAX_TEXT_LEN = 32

_CPU_SAMPLE_SECONDS = 1.0

#: Linux pseudo-filesystems that are not real storage. Volumes mounted on
#: these are skipped. Windows drive letters are unaffected by this set.
_PSEUDO_FSTYPES = frozenset(
    {
        "tmpfs",
        "devtmpfs",
        "proc",
        "sysfs",
        "cgroup",
        "cgroup2",
        "overlay",
        "squashfs",
        "nsfs",
        "debugfs",
        "tracefs",
        "securityfs",
        "configfs",
        "fusectl",
        "mqueue",
        "shm",
        "devpts",
        "autofs",
        "binfmt_misc",
    }
)


class CollectionError(RuntimeError):
    """A required measurement failed or was invalid. Skip the heartbeat."""


@dataclass(frozen=True)
class VolumeSample:
    """One accessible local volume. All values are validated."""

    label: str
    disk_percent: float
    used_bytes: int
    total_bytes: int


@dataclass(frozen=True)
class MetricSample:
    """One collection cycle. Percentages are 0-100; byte counts are >= 0."""

    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    volumes: tuple[VolumeSample, ...] = field(default_factory=tuple)


def _valid_percent(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0.0 <= number <= 100.0:
        return None
    return number


def _valid_bytes(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            return None
        value = int(value)
    if not isinstance(value, int) or value < 0:
        return None
    return value


def collect_cpu(sample_seconds: float = _CPU_SAMPLE_SECONDS) -> float:
    """Return host CPU utilization percent (blocking short sample)."""
    try:
        raw = psutil.cpu_percent(interval=sample_seconds)
    except Exception as exc:
        raise CollectionError(f"CPU collection failed: {type(exc).__name__}") from exc
    percent = _valid_percent(raw)
    if percent is None:
        raise CollectionError("CPU collection returned an invalid value.")
    return percent


def collect_memory() -> tuple[float, int | None, int | None]:
    """Return ``(percent, used_bytes, total_bytes)`` for virtual memory."""
    try:
        mem = psutil.virtual_memory()
    except Exception as exc:
        raise CollectionError(f"Memory collection failed: {type(exc).__name__}") from exc
    percent = _valid_percent(getattr(mem, "percent", None))
    if percent is None:
        raise CollectionError("Memory collection returned an invalid percent.")
    return (
        percent,
        _valid_bytes(getattr(mem, "used", None)),
        _valid_bytes(getattr(mem, "total", None)),
    )


def _volume_label(device: str, mountpoint: str, system: str) -> str | None:
    if system == "Windows":
        # psutil reports "C:\\" — the M4 example uses "C:".
        label = device.rstrip("\\").rstrip("/")
    else:
        label = mountpoint
    label = (label or "").strip()
    if not label or len(label) > MAX_LABEL_LEN:
        return None
    return label


def discover_volumes(system: str | None = None) -> list[VolumeSample]:
    """List accessible local volumes, skipping anything unusable.

    Pseudo-filesystems, inaccessible mount points (permission or transient
    OS errors), and volumes with invalid measurements are omitted with a
    debug-level diagnostic — never reported as zero.
    """
    active = system or _platform.system()
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception as exc:
        log.debug("volume discovery failed: %s", type(exc).__name__)
        return []
    volumes: list[VolumeSample] = []
    for part in partitions:
        if not part.mountpoint:
            continue
        if active != "Windows" and (part.fstype or "").lower() in _PSEUDO_FSTYPES:
            continue
        label = _volume_label(part.device or "", part.mountpoint, active)
        if label is None:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            log.debug("skipping inaccessible volume at %s", part.mountpoint)
            continue
        except Exception as exc:  # transient psutil failure: omit, keep going
            log.debug(
                "skipping volume at %s (%s)", part.mountpoint, type(exc).__name__
            )
            continue
        percent = _valid_percent(getattr(usage, "percent", None))
        used = _valid_bytes(getattr(usage, "used", None))
        total = _valid_bytes(getattr(usage, "total", None))
        if percent is None or used is None or total is None:
            log.debug("skipping volume with invalid measurements at %s", part.mountpoint)
            continue
        volumes.append(
            VolumeSample(
                label=label, disk_percent=percent, used_bytes=used, total_bytes=total
            )
        )
        if len(volumes) >= MAX_VOLUMES:
            break
    return volumes


def current_platform() -> str | None:
    """Return the running OS name for the heartbeat, or None if unusable.

    The M4 schema requires a non-blank value of at most 32 chars, so
    anything outside that range is reported as absent rather than mangled.
    """
    name = (_platform.system() or "").strip()
    if not name or len(name) > MAX_TEXT_LEN:
        return None
    return name


def collect_metrics(system: str | None = None) -> MetricSample:
    """Collect one full approved-inventory sample."""
    cpu = collect_cpu()
    memory_percent, memory_used, memory_total = collect_memory()
    volumes = discover_volumes(system=system)
    return MetricSample(
        cpu_percent=cpu,
        memory_percent=memory_percent,
        memory_used_bytes=memory_used,
        memory_total_bytes=memory_total,
        volumes=tuple(volumes),
    )
