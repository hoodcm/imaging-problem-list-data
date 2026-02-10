"""Test configuration and fixtures."""

from collections.abc import Iterator

import pytest

from finding_extractor.config import clear_settings_cache


@pytest.fixture(autouse=True)
def _clear_cached_settings() -> Iterator[None]:
    """Ensure env var mutations in tests do not leak through the settings cache."""
    clear_settings_cache()
    yield
    clear_settings_cache()
