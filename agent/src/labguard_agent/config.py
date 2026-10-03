"""Environment-based configuration for the LabGuard agent (M5).

Reads ``LABGUARD_*`` variables, validates them at startup, and fails fast
with actionable errors. The bearer token is never logged, never printed,
and never interpolated into error messages.

Device identity is intentionally *not* configured here: the M4 server
derives it from the bearer credential, so there is no ``LABGUARD_DEVICE_ID``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

MIN_INTERVAL_SECONDS = 10.0
MAX_INTERVAL_SECONDS = 3600.0
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 300.0
DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(ValueError):
    """Raised when agent configuration is missing or invalid."""


@dataclass(frozen=True)
class AgentConfig:
    """Validated agent configuration. ``agent_token`` must stay secret."""

    api_base_url: str
    agent_token: str
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    log_level: str = DEFAULT_LOG_LEVEL


def _parse_float(raw: str, name: str, minimum: float, maximum: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConfigError(
            f"{name} must be a number between {minimum:g} and {maximum:g} seconds."
        ) from None
    # Reject NaN/inf explicitly: float() accepts "nan"/"inf".
    if not minimum <= value <= maximum:
        raise ConfigError(
            f"{name} must be a number between {minimum:g} and {maximum:g} seconds."
        )
    return value


def _validate_base_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ConfigError(
            "LABGUARD_API_BASE_URL is required, e.g. "
            "http://192.0.2.10:8000 for a LAN server."
        )
    try:
        parts = urlsplit(value)
    except ValueError:
        raise ConfigError(
            "LABGUARD_API_BASE_URL is not a valid URL, e.g. "
            "http://192.0.2.10:8000."
        ) from None
    if parts.scheme not in ("http", "https"):
        raise ConfigError(
            "LABGUARD_API_BASE_URL must start with http:// or https:// "
            "(use https:// outside isolated local development)."
        )
    if not parts.hostname:
        raise ConfigError(
            "LABGUARD_API_BASE_URL must include a host, e.g. "
            "http://192.0.2.10:8000."
        )
    if parts.username or parts.password:
        raise ConfigError(
            "LABGUARD_API_BASE_URL must not embed credentials; "
            "the agent authenticates with LABGUARD_AGENT_TOKEN."
        )
    return value.rstrip("/")


def _validate_log_level(raw: str | None) -> str:
    if raw is None:
        return DEFAULT_LOG_LEVEL
    level = raw.strip().upper()
    if level in LOG_LEVELS:
        return level
    # Lenient on purpose: an unknown level must not stop reporting.
    # The caller logs a warning naming the bad value (never a secret).
    return DEFAULT_LOG_LEVEL


def load_config(env: Mapping[str, str] | None = None) -> AgentConfig:
    """Build an :class:`AgentConfig` from environment variables.

    Raises :class:`ConfigError` with actionable messages. Error messages
    never contain the token value.
    """
    source: Mapping[str, str] = os.environ if env is None else env

    base_url = _validate_base_url(source.get("LABGUARD_API_BASE_URL", ""))

    token = (source.get("LABGUARD_AGENT_TOKEN") or "").strip()
    if not token:
        raise ConfigError(
            "LABGUARD_AGENT_TOKEN is required. Issue one with "
            "POST /api/v1/devices/{id}/enrollment-token (lab manager) "
            "and set it as an environment variable."
        )

    raw_interval = (source.get("LABGUARD_INTERVAL_SECONDS") or "").strip()
    interval = (
        _parse_float(
            raw_interval,
            "LABGUARD_INTERVAL_SECONDS",
            MIN_INTERVAL_SECONDS,
            MAX_INTERVAL_SECONDS,
        )
        if raw_interval
        else DEFAULT_INTERVAL_SECONDS
    )

    raw_timeout = (source.get("LABGUARD_REQUEST_TIMEOUT_SECONDS") or "").strip()
    timeout = (
        _parse_float(
            raw_timeout,
            "LABGUARD_REQUEST_TIMEOUT_SECONDS",
            MIN_TIMEOUT_SECONDS,
            MAX_TIMEOUT_SECONDS,
        )
        if raw_timeout
        else DEFAULT_TIMEOUT_SECONDS
    )

    return AgentConfig(
        api_base_url=base_url,
        agent_token=token,
        interval_seconds=interval,
        request_timeout_seconds=timeout,
        log_level=_validate_log_level(source.get("LABGUARD_LOG_LEVEL")),
    )
