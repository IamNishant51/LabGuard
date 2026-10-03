"""Client tests: auth, retry bounds, Retry-After, failures, secret safety."""

import logging
import threading

import httpx
import pytest

from labguard_agent.client import AuthError, DeliveryError, HeartbeatClient

TOKEN = "secret-token-xyz-999"
PAYLOAD = {
    "platform": "Windows",
    "agent_version": "0.1.0",
    "agent_timestamp": "2026-10-03T12:00:00+00:00",
    "metrics": {"cpu_percent": 10.0, "memory_percent": 20.0, "volumes": []},
}
OK_BODY = {"accepted": True, "server_time": "2026-10-03T12:00:01+00:00"}


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=OK_BODY)


def _make_client(
    handler: object,
    *,
    max_attempts: int = 4,
    jitter: float = 0.0,
) -> tuple[HeartbeatClient, list[float], list[int]]:
    sleeps: list[float] = []
    calls: list[int] = []

    def counting_handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return handler(request)  # type: ignore[operator]

    client = HeartbeatClient(
        base_url="http://192.0.2.10:8000",
        token=TOKEN,
        timeout_seconds=5,
        max_attempts=max_attempts,
        sleep_fn=sleeps.append,
        jitter_fn=lambda cap: jitter,
        transport=httpx.MockTransport(counting_handler),
    )
    return client, sleeps, calls


def test_success_sends_bearer_and_path() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.url.path
        seen["method"] = request.method
        return _ok(request)

    client, sleeps, calls = _make_client(handler)
    try:
        result = client.send(PAYLOAD)
    finally:
        client.close()
    assert result.accepted is True
    assert result.server_time == OK_BODY["server_time"]
    assert result.attempts == 1
    assert seen == {
        "auth": f"Bearer {TOKEN}",
        "path": "/api/v1/agent/heartbeat",
        "method": "POST",
    }
    assert sleeps == []
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_stop_immediately(status: int, caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": "UNAUTHENTICATED"}})

    client, sleeps, calls = _make_client(handler)
    try:
        with caplog.at_level(logging.INFO):
            with pytest.raises(AuthError) as excinfo:
                client.send(PAYLOAD)
    finally:
        client.close()
    assert len(calls) == 1
    assert sleeps == []
    assert "LABGUARD_AGENT_TOKEN" in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)
    assert TOKEN not in caplog.text


def test_429_honors_retry_after() -> None:
    responses = [
        httpx.Response(429, headers={"retry-after": "2"}),
        httpx.Response(200, json=OK_BODY),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    client, sleeps, calls = _make_client(handler)
    try:
        result = client.send(PAYLOAD)
    finally:
        client.close()
    assert result.attempts == 2
    assert sleeps == [2.0]


def test_429_invalid_retry_after_falls_back_to_backoff() -> None:
    responses = [
        httpx.Response(429, headers={"retry-after": "soon"}),
        httpx.Response(200, json=OK_BODY),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    client, sleeps, _ = _make_client(handler)
    try:
        client.send(PAYLOAD)
    finally:
        client.close()
    assert sleeps == [1.0]  # base delay 1s, jitter 0


def test_5xx_retries_with_exponential_backoff_then_succeeds() -> None:
    responses = [
        httpx.Response(500),
        httpx.Response(503),
        httpx.Response(200, json=OK_BODY),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    client, sleeps, calls = _make_client(handler)
    try:
        result = client.send(PAYLOAD)
    finally:
        client.close()
    assert result.attempts == 3
    assert sleeps == [1.0, 2.0]
    assert len(calls) == 3


def test_5xx_always_fails_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client, sleeps, calls = _make_client(handler, max_attempts=3)
    try:
        with pytest.raises(DeliveryError, match="3 attempts"):
            client.send(PAYLOAD)
    finally:
        client.close()
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_timeout_and_connection_errors_retried() -> None:
    errors: list = [httpx.TimeoutException("slow"), httpx.ConnectError("dns")]

    def handler(request: httpx.Request) -> httpx.Response:
        error = errors.pop(0)
        if isinstance(error, Exception):
            raise error
        return httpx.Response(200, json=OK_BODY)

    errors.append("ok")
    client, sleeps, calls = _make_client(handler)
    try:
        result = client.send(PAYLOAD)
    finally:
        client.close()
    assert result.attempts == 3
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize("status", [400, 404, 422])
def test_permanent_4xx_not_retried(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    client, sleeps, calls = _make_client(handler)
    try:
        with pytest.raises(DeliveryError, match=f"HTTP {status}"):
            client.send(PAYLOAD)
    finally:
        client.close()
    assert len(calls) == 1
    assert sleeps == []


def test_retry_delay_capped_despite_large_jitter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client, sleeps, _ = _make_client(handler, max_attempts=8, jitter=9999.0)
    try:
        with pytest.raises(DeliveryError):
            client.send(PAYLOAD)
    finally:
        client.close()
    # Jitter can at most double the per-attempt cap; the total never exceeds 30s.
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_invalid_success_body_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accepted": False})

    client, _, _ = _make_client(handler)
    try:
        with pytest.raises(DeliveryError):
            client.send(PAYLOAD)
    finally:
        client.close()


def test_token_never_in_logs_or_errors(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client, _, _ = _make_client(handler, max_attempts=2)
    try:
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(DeliveryError) as excinfo:
                client.send(PAYLOAD)
    finally:
        client.close()
    assert TOKEN not in caplog.text
    assert TOKEN not in str(excinfo.value)


def test_stop_event_aborts_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    stop = threading.Event()
    stop.set()
    client, _, _ = _make_client(handler)
    try:
        with pytest.raises(DeliveryError, match="aborted"):
            client.send(PAYLOAD, stop_event=stop)
    finally:
        client.close()
