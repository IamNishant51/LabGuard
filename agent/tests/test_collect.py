"""Collection tests with mocked psutil and platform inputs."""

from types import SimpleNamespace

import pytest

from labguard_agent import collect
from labguard_agent.collect import (
    CollectionError,
    MetricSample,
    collect_cpu,
    collect_memory,
    collect_metrics,
    current_platform,
    discover_volumes,
)


def _part(device: str, mountpoint: str, fstype: str = "") -> SimpleNamespace:
    return SimpleNamespace(device=device, mountpoint=mountpoint, fstype=fstype)


def _usage(percent: float, used: int, total: int) -> SimpleNamespace:
    return SimpleNamespace(percent=percent, used=used, total=total)


def test_collect_cpu_uses_psutil_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_cpu_percent(interval: float | None = None) -> float:
        seen["interval"] = interval
        return 24.8

    monkeypatch.setattr(collect.psutil, "cpu_percent", fake_cpu_percent)
    assert collect_cpu() == 24.8
    assert seen["interval"] == 1.0


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), -1.0, 100.5, "x", None, True])
def test_collect_cpu_rejects_invalid(raw: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect.psutil, "cpu_percent", lambda interval=None: raw)
    with pytest.raises(CollectionError):
        collect_cpu()


def test_collect_cpu_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(interval: float | None = None) -> float:
        raise RuntimeError("sensor gone")

    monkeypatch.setattr(collect.psutil, "cpu_percent", boom)
    with pytest.raises(CollectionError, match="CPU"):
        collect_cpu()


def test_collect_memory_maps_units(monkeypatch: pytest.MonkeyPatch) -> None:
    mem = SimpleNamespace(percent=68.2, used=7300000000, total=16000000000)
    monkeypatch.setattr(collect.psutil, "virtual_memory", lambda: mem)
    percent, used, total = collect_memory()
    assert (percent, used, total) == (68.2, 7300000000, 16000000000)


def test_collect_memory_invalid_percent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    mem = SimpleNamespace(percent=float("nan"), used=1, total=2)
    monkeypatch.setattr(collect.psutil, "virtual_memory", lambda: mem)
    with pytest.raises(CollectionError):
        collect_memory()


def test_windows_volume_discovery_drive_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collect.psutil,
        "disk_partitions",
        lambda all=False: [_part("C:\\", "C:\\", "NTFS"), _part("D:\\", "D:\\", "NTFS")],
    )
    usages = {"C:\\": _usage(71.4, 250000000000, 350000000000)}

    def fake_usage(path: str) -> SimpleNamespace:
        if path not in usages:
            raise PermissionError("denied")
        return usages[path]

    monkeypatch.setattr(collect.psutil, "disk_usage", fake_usage)
    volumes = discover_volumes(system="Windows")
    # C: reported with its real numbers; D: omitted (inaccessible), never zero.
    assert [(v.label, v.disk_percent, v.used_bytes, v.total_bytes) for v in volumes] == [
        ("C:", 71.4, 250000000000, 350000000000)
    ]


def test_linux_volume_discovery_skips_pseudo_filesystems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        collect.psutil,
        "disk_partitions",
        lambda all=False: [
            _part("/dev/sda1", "/", "ext4"),
            _part("tmpfs", "/run", "tmpfs"),
            _part("proc", "/proc", "proc"),
            _part("/dev/sda2", "/home", "ext4"),
        ],
    )
    monkeypatch.setattr(
        collect.psutil, "disk_usage", lambda path: _usage(10.0, 100, 1000)
    )
    volumes = discover_volumes(system="Linux")
    assert [v.label for v in volumes] == ["/", "/home"]


def test_inaccessible_and_invalid_volumes_omitted_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        collect.psutil,
        "disk_partitions",
        lambda all=False: [
            _part("/dev/sda1", "/", "ext4"),
            _part("", "", "ext4"),  # empty mountpoint: skipped
            _part("/dev/sdb1", "/media/usb", "vfat"),
        ],
    )

    def fake_usage(path: str) -> SimpleNamespace:
        if path == "/media/usb":
            raise OSError("transient I/O error")
        return _usage(50.0, 500, 1000)

    monkeypatch.setattr(collect.psutil, "disk_usage", fake_usage)
    volumes = discover_volumes(system="Linux")
    assert [v.label for v in volumes] == ["/"]
    assert all(v.used_bytes > 0 for v in volumes)


def test_partition_enumeration_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(all: bool = False) -> list:
        raise RuntimeError("nope")

    monkeypatch.setattr(collect.psutil, "disk_partitions", boom)
    assert discover_volumes(system="Linux") == []


def test_current_platform_reports_os(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect._platform, "system", lambda: "Windows")
    assert current_platform() == "Windows"


def test_current_platform_blank_or_long_becomes_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collect._platform, "system", lambda: "   ")
    assert current_platform() is None
    monkeypatch.setattr(collect._platform, "system", lambda: "X" * 33)
    assert current_platform() is None


def test_collect_metrics_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect.psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(
        collect.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=40.0, used=400, total=1000),
    )
    monkeypatch.setattr(
        collect.psutil, "disk_partitions", lambda all=False: [_part("/", "/", "ext4")]
    )
    monkeypatch.setattr(collect.psutil, "disk_usage", lambda path: _usage(20.0, 200, 1000))
    sample = collect_metrics(system="Linux")
    assert isinstance(sample, MetricSample)
    assert sample.cpu_percent == 12.5
    assert sample.memory_percent == 40.0
    assert [v.label for v in sample.volumes] == ["/"]
