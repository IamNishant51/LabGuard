"""Foreground entry point: ``python -m labguard_agent`` (M5)."""

from __future__ import annotations

import logging
import signal
import sys

from labguard_agent.config import ConfigError, load_config
from labguard_agent.runner import AgentRunner

log = logging.getLogger("labguard_agent")


def main(argv: list[str] | None = None) -> int:
    """Validate config, run the heartbeat loop, shut down cleanly."""
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"labguard-agent: configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # The startup line names the destination, cadence, and identity the
    # server will see — never the credential.
    log.info(
        "labguard-agent starting: url=%s interval=%.0fs timeout=%.0fs level=%s",
        config.api_base_url,
        config.interval_seconds,
        config.request_timeout_seconds,
        config.log_level,
    )
    runner = AgentRunner(config)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda _n, _f: runner.request_stop())
        except (OSError, ValueError, RuntimeError):
            continue
    try:
        return runner.run()
    except KeyboardInterrupt:
        runner.request_stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())
