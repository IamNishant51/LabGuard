"""Runner tests: periodic cycles, no overlap, shutdown, cleanup, no queue."""

import threading
import time

from labguard_agent.client import AuthError, DeliveryError, HeartbeatResult
from labguard_agent.collect import CollectionError, MetricSample
from labguard_agent.config import AgentConfig
from labguard_agent.runner import AgentRunner

SAMPLE = MetricSample(
    cpu_percent=10.0,
    memory_percent=20.0,
    memory_used_bytes=200,
    memory_total_bytes=1000,
    volumes=(),
)


def _config(**overrides: object) -> AgentConfig:
    base: dict = {
        "api_base_url": "http://192.0.2.10:8000",
        "agent_token": "tok",
        "interval_seconds": 30.0,
        "request_timeout_seconds": 5.0,
        "log_level": "INFO",
    }
    base.update(overrides)
    return AgentConfig(**base)  # type: ignore[arg-type]


class FakeClient:
    """Stand-in for HeartbeatClient with overlap detection."""

    def __init__(self, behavior: str = "ok") -> None:
        self.behavior = behavior
        self.sends: list[dict] = []
        self.closed = False
        self._in_send = False
        self.overlap = False

    def send(self, payload: dict, stop_event: object = None) -> HeartbeatResult:
        if self._in_send:
            self.overlap = True
        self._in_send = True
        try:
            self.sends.append(payload)
            if self.behavior == "auth":
                raise AuthError("rejected")
            if self.behavior == "fail":
                raise DeliveryError("down")
            return HeartbeatResult(accepted=True, server_time="t", attempts=1)
        finally:
            self._in_send = False

    def close(self) -> None:
        self.closed = True


def test_run_once_success_builds_exact_payload() -> None:
    client = FakeClient()
    runner = AgentRunner(_config(), collect_fn=lambda: SAMPLE)
    assert runner.run_once(client) is True
    (payload,) = client.sends
    assert set(payload) == {"platform", "agent_version", "agent_timestamp", "metrics"}
    assert payload["metrics"]["cpu_percent"] == 10.0


def test_run_once_collection_failure_skips_send() -> None:
    def boom() -> MetricSample:
        raise CollectionError("sensor gone")

    client = FakeClient()
    runner = AgentRunner(_config(), collect_fn=boom)
    assert runner.run_once(client) is False
    assert client.sends == []


def test_run_once_auth_and_delivery_failures_return_false() -> None:
    runner = AgentRunner(_config(), collect_fn=lambda: SAMPLE)
    assert runner.run_once(FakeClient("auth")) is False
    assert runner.run_once(FakeClient("fail")) is False


def test_periodic_run_no_overlap_cleanup_and_exit_code() -> None:
    client = FakeClient()
    cycles = threading.Event()
    original_send = client.send

    def counting_send(payload: dict, stop_event: object = None) -> HeartbeatResult:
        result = original_send(payload, stop_event)
        if len(client.sends) >= 3:
            cycles.set()
        return result

    client.send = counting_send  # type: ignore[method-assign]
    runner = AgentRunner(
        _config(interval_seconds=0.05),
        client_factory=lambda: client,
        collect_fn=lambda: SAMPLE,
    )
    thread = threading.Thread(target=runner.run)
    thread.start()
    assert cycles.wait(timeout=10)
    runner.request_stop()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(client.sends) >= 3
    assert client.overlap is False
    assert client.closed is True


def test_failed_heartbeats_do_not_tight_loop() -> None:
    client = FakeClient("fail")
    runner = AgentRunner(
        _config(interval_seconds=50.0),
        client_factory=lambda: client,
        collect_fn=lambda: SAMPLE,
    )
    thread = threading.Thread(target=runner.run)
    thread.start()
    time.sleep(0.5)
    runner.request_stop()
    thread.join(timeout=10)
    # One failed cycle, then waiting for the deadline — not a spin.
    assert len(client.sends) == 1
    assert client.closed is True


def test_no_local_telemetry_queue() -> None:
    client = FakeClient("fail")
    runner = AgentRunner(_config(), collect_fn=lambda: SAMPLE)
    assert runner.run_once(client) is False
    assert runner.run_once(client) is False
    assert len(client.sends) == 2
    for name in ("queue", "backlog", "pending", "outbox", "buffer"):
        assert not hasattr(runner, name)


def test_request_stop_before_run_exits_immediately() -> None:
    client = FakeClient()
    runner = AgentRunner(
        _config(interval_seconds=50.0),
        client_factory=lambda: client,
        collect_fn=lambda: SAMPLE,
    )
    runner.request_stop()
    assert runner.run() == 0
    assert client.sends == []
    assert client.closed is True
