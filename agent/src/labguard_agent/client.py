"""Authenticated heartbeat HTTP client with bounded retries (M5).

Sends the exact M4 payload to ``POST /api/v1/agent/heartbeat`` with the
device bearer token, over a single reused ``httpx.Client`` with explicit
timeouts. TLS verification is never disabled.

Retry policy per heartbeat cycle (never unbounded, never queued):
- ``401``/``403``: stop immediately, raise :class:`AuthError` with an
  actionable credential diagnostic (the token is never logged).
- ``429``: retry honoring a valid ``Retry-After`` (seconds, capped).
- ``5xx`` and network failures (connection, timeout, DNS/TLS): retry with
  exponential backoff plus jitter, capped in attempts and delay.
- Other ``4xx``: permanent, raise :class:`DeliveryError` without retry.

``sleep_fn`` and ``jitter_fn`` are injectable so tests stay deterministic.
``stop_event`` (a ``threading.Event``) aborts backoff sleep promptly for
graceful shutdown.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable

import httpx

log = logging.getLogger(__name__)

HEARTBEAT_PATH = "/api/v1/agent/heartbeat"
MAX_ATTEMPTS = 4
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0


class AuthError(RuntimeError):
    """Credential rejected (401/403). Check or re-issue the device token."""


class DeliveryError(RuntimeError):
    """Heartbeat could not be delivered (network, 5xx, permanent 4xx)."""


@dataclass(frozen=True)
class HeartbeatResult:
    accepted: bool
    server_time: str | None
    attempts: int


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse a ``Retry-After`` delta-seconds header; None if unusable."""
    if value is None:
        return None
    try:
        delay = float(value.strip())
    except (TypeError, ValueError):
        return None
    if delay != delay or delay < 0:  # NaN or negative
        return None
    return min(delay, MAX_DELAY_SECONDS)


def _backoff_delay(attempt: int, jitter_fn: Callable[[float], float]) -> float:
    cap = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2.0 ** (attempt - 1)))
    jitter = jitter_fn(cap)
    if jitter != jitter or jitter < 0:  # misbehaving injection: ignore
        jitter = 0.0
    return min(MAX_DELAY_SECONDS, cap + min(jitter, cap))


class HeartbeatClient:
    """Reusable authenticated client. Create once per process; close on exit."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        max_attempts: int = MAX_ATTEMPTS,
        sleep_fn: Callable[[float], None] = time.sleep,
        jitter_fn: Callable[[float], float] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._max_attempts = max(1, max_attempts)
        self._sleep = sleep_fn
        self._jitter = jitter_fn or (lambda cap: random.uniform(0, cap))
        # One bounded-lifetime client for all heartbeats; verify=True default.
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HeartbeatClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _sleep_or_abort(self, delay: float, stop_event: threading.Event | None) -> bool:
        """Sleep in small chunks so shutdown stays prompt. True if aborted."""
        if stop_event is None:
            self._sleep(delay)
            return False
        deadline = time.monotonic() + delay
        while True:
            if stop_event.is_set():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._sleep(min(0.2, remaining))

    def send(
        self, payload: dict, stop_event: threading.Event | None = None
    ) -> HeartbeatResult:
        """POST one heartbeat with bounded retries. Never logs the token."""
        attempts = 0
        while True:
            attempts += 1
            response: httpx.Response | None = None
            reason: str | None = None
            try:
                response = self._http.post(HEARTBEAT_PATH, json=payload)
            except httpx.TimeoutException:
                reason = "timeout"
            except httpx.TransportError as exc:
                # Connection, DNS, TLS, and protocol failures land here.
                log.debug("heartbeat network failure: %s", type(exc).__name__)
                reason = "network"
            except httpx.HTTPError as exc:
                raise DeliveryError(
                    f"heartbeat failed: {type(exc).__name__}"
                ) from exc
            else:
                outcome = self._handle_response(response, attempts)
                if isinstance(outcome, HeartbeatResult):
                    return outcome
                reason = outcome
            # Permanent failures raise inside _handle_response; reaching here
            # means the failure is retryable (timeout/network/429/5xx).
            if attempts >= self._max_attempts:
                raise DeliveryError(
                    f"heartbeat failed after {attempts} attempts ({reason})."
                )
            delay = self._pending_delay(response, attempts)
            log.info(
                "heartbeat attempt %d failed (%s); retrying in %.1fs",
                attempts,
                reason,
                delay,
            )
            if self._sleep_or_abort(delay, stop_event):
                raise DeliveryError("heartbeat aborted during shutdown.")

    def _pending_delay(
        self, response: httpx.Response | None, attempts: int
    ) -> float:
        if response is not None and response.status_code == 429:
            retry_after = _retry_after_seconds(response.headers.get("retry-after"))
            if retry_after is not None:
                return retry_after
        return _backoff_delay(attempts, self._jitter)

    def _handle_response(
        self, response: httpx.Response, attempts: int
    ) -> HeartbeatResult | str:
        status = response.status_code
        if status == 200:
            try:
                body = response.json()
            except ValueError:
                raise DeliveryError("heartbeat failed: invalid server response.") from None
            if not isinstance(body, dict) or body.get("accepted") is not True:
                raise DeliveryError("heartbeat failed: invalid server response.")
            server_time = body.get("server_time")
            log.info("heartbeat accepted (attempt %d).", attempts)
            return HeartbeatResult(
                accepted=True,
                server_time=str(server_time) if server_time is not None else None,
                attempts=attempts,
            )
        if status in (401, 403):
            raise AuthError(
                "Server rejected the device credential (HTTP "
                f"{status}). Check LABGUARD_AGENT_TOKEN, re-issue it with "
                "POST /api/v1/devices/{id}/enrollment-token, or ask the lab "
                "manager whether this device was revoked or deactivated."
            )
        if status == 429 or 500 <= status <= 599:
            return "retryable-status"
        raise DeliveryError(
            f"heartbeat failed: server returned HTTP {status} (not retried)."
        )
