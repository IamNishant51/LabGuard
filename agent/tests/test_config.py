"""Config validation tests: valid, missing, malformed, and secret-safe."""

import pytest

from labguard_agent.config import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    AgentConfig,
    ConfigError,
    load_config,
)

TOKEN = "test-token-value-abc123"
BASE = {"LABGUARD_API_BASE_URL": "http://192.0.2.10:8000", "LABGUARD_AGENT_TOKEN": TOKEN}


def test_valid_minimal_config_uses_defaults() -> None:
    config = load_config(dict(BASE))
    assert isinstance(config, AgentConfig)
    assert config.api_base_url == "http://192.0.2.10:8000"
    assert config.agent_token == TOKEN
    assert config.interval_seconds == DEFAULT_INTERVAL_SECONDS
    assert config.request_timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.log_level == "INFO"


def test_valid_full_config() -> None:
    env = dict(
        BASE,
        LABGUARD_INTERVAL_SECONDS="30",
        LABGUARD_REQUEST_TIMEOUT_SECONDS="5",
        LABGUARD_LOG_LEVEL="debug",
    )
    config = load_config(env)
    assert config.interval_seconds == 30.0
    assert config.request_timeout_seconds == 5.0
    assert config.log_level == "DEBUG"


def test_trailing_slash_stripped() -> None:
    env = dict(BASE, LABGUARD_API_BASE_URL="http://192.0.2.10:8000/")
    assert load_config(env).api_base_url == "http://192.0.2.10:8000"


def test_missing_url_and_token_rejected() -> None:
    with pytest.raises(ConfigError, match="LABGUARD_API_BASE_URL"):
        load_config({"LABGUARD_AGENT_TOKEN": TOKEN})
    with pytest.raises(ConfigError, match="LABGUARD_AGENT_TOKEN"):
        load_config({"LABGUARD_API_BASE_URL": "http://192.0.2.10:8000"})
    with pytest.raises(ConfigError):
        load_config({})


def test_blank_token_rejected_without_echo() -> None:
    env = dict(BASE, LABGUARD_AGENT_TOKEN="   ")
    with pytest.raises(ConfigError) as excinfo:
        load_config(env)
    assert TOKEN not in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://192.0.2.10/data",
        "http://",
        "http://user:pass@192.0.2.10:8000",
        "",
        "   ",
    ],
)
def test_invalid_urls_rejected(url: str) -> None:
    with pytest.raises(ConfigError, match="LABGUARD_API_BASE_URL"):
        load_config({"LABGUARD_API_BASE_URL": url, "LABGUARD_AGENT_TOKEN": TOKEN})


@pytest.mark.parametrize("name", ["LABGUARD_INTERVAL_SECONDS", "LABGUARD_REQUEST_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("raw", ["zero", "NaN", "inf", "-inf", "-5", "0x"])
def test_invalid_numerics_rejected(name: str, raw: str) -> None:
    with pytest.raises(ConfigError, match=name):
        load_config(dict(BASE, **{name: raw}))


@pytest.mark.parametrize("name", ["LABGUARD_INTERVAL_SECONDS", "LABGUARD_REQUEST_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_numerics_fall_back_to_default(name: str, raw: str) -> None:
    config = load_config(dict(BASE, **{name: raw}))
    assert config.interval_seconds == DEFAULT_INTERVAL_SECONDS
    assert config.request_timeout_seconds == DEFAULT_TIMEOUT_SECONDS


def test_interval_below_minimum_rejected() -> None:
    with pytest.raises(ConfigError, match="LABGUARD_INTERVAL_SECONDS"):
        load_config(dict(BASE, LABGUARD_INTERVAL_SECONDS="9.9"))


def test_interval_at_minimum_accepted() -> None:
    assert load_config(dict(BASE, LABGUARD_INTERVAL_SECONDS="10")).interval_seconds == 10.0


def test_interval_above_maximum_rejected() -> None:
    with pytest.raises(ConfigError, match="LABGUARD_INTERVAL_SECONDS"):
        load_config(dict(BASE, LABGUARD_INTERVAL_SECONDS="3601"))


def test_timeout_bounds_enforced() -> None:
    with pytest.raises(ConfigError, match="LABGUARD_REQUEST_TIMEOUT_SECONDS"):
        load_config(dict(BASE, LABGUARD_REQUEST_TIMEOUT_SECONDS="0.5"))
    with pytest.raises(ConfigError, match="LABGUARD_REQUEST_TIMEOUT_SECONDS"):
        load_config(dict(BASE, LABGUARD_REQUEST_TIMEOUT_SECONDS="301"))


def test_unknown_log_level_falls_back_to_info() -> None:
    config = load_config(dict(BASE, LABGUARD_LOG_LEVEL="verbose-please"))
    assert config.log_level == "INFO"


def test_no_device_id_supported() -> None:
    """M4 derives identity from the bearer credential; no DEVICE_ID exists."""
    config = load_config(dict(BASE, LABGUARD_DEVICE_ID="LAB-PC-001"))
    assert not hasattr(config, "device_id")
