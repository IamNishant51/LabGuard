"""Foreground run loop: periodic collect-and-send with graceful shutdown (M5).

One cycle = collect approved metrics, build the M4 payload, send it with
bounded retries. Cycles never overlap (strictly sequential), failures never
create a tight loop (the next cycle always waits for its scheduled
deadline), and nothing is queued locally — a failed sample is reported and
dropped.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Protocol

import labguard_agent
from labguard_agent import collect as _collect
from labguard_agent.client import (
    AuthError,
    DeliveryError,
    HeartbeatClient,
    HeartbeatResult,
)
from labguard_agent.collect import CollectionError
from labguard_agent.config import AgentConfig
from labguard_agent.payload import build_heartbeat_payload

log = logging.getLogger(__name__)


class HeartbeatSender(Protocol):
    """Minimal client surface the loop needs (real or fake in tests)."""

    def send(
        self, payload: dict, stop_event: threading.Event | None = None
    ) -> HeartbeatResult:
        ...

    def close(self) -> None:
        ...


class AgentRunner:
    """Owns the periodic loop. ``run()`` blocks until ``request_stop()``."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        client_factory: Callable[[], HeartbeatSender] | None = None,
        collect_fn: Callable[[], _collect.MetricSample] | None = None,
    ) -> None:
        self._config = config
        self._stop = threading.Event()
        self._client_factory = client_factory or (
            lambda: HeartbeatClient(
                base_url=config.api_base_url,
                token=config.agent_token,
                timeout_seconds=config.request_timeout_seconds,
            )
        )
        self._collect = collect_fn or _collect.collect_metrics

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def run_once(self, client: HeartbeatSender) -> bool:
        """Run a single collect-and-send cycle. True if accepted."""
        try:
            sample = self._collect()
        except CollectionError as exc:
            log.warning("heartbeat skipped: %s", exc)
            return False
        payload = build_heartbeat_payload(
            platform=_collect.current_platform(),
            agent_version=labguard_agent.__version__,
            agent_timestamp=datetime.now(timezone.utc),
            sample=sample,
        )
        try:
            result = client.send(payload, stop_event=self._stop)
        except AuthError as exc:
            log.error("%s", exc)
            return False
        except DeliveryError as exc:
            log.warning("%s", exc)
            return False
        return result.accepted

    def run(self) -> int:
        """Loop until stopped. Returns a process exit code (0 = clean)."""
        interval = self._config.interval_seconds
        log.info(
            "heartbeat loop started: every %.0fs to %s",
            interval,
            self._config.api_base_url,
        )
        client = self._client_factory()
        try:
            while not self._stop.is_set():
                cycle_start = time.monotonic()
                self.run_once(client)
                wait = interval - (time.monotonic() - cycle_start)
                if wait > 0:
                    self._stop.wait(wait)
        finally:
            client.close()
        log.info("heartbeat loop stopped.")
        return 0
