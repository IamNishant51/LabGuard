"""M1 agent skeleton tests: package imports cleanly and versions correctly."""

import labguard_agent


def test_version_is_defined() -> None:
    assert labguard_agent.__version__ == "0.1.0"


def test_import_has_no_collection_side_effects() -> None:
    # Skeleton must not collect metrics or touch the network on import.
    # psutil/httpx are declared dependencies for M5+, not used in M1.
    assert labguard_agent.__all__ == ["__version__"]
