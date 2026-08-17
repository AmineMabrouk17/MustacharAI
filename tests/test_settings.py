"""Tests for application settings."""

from mustachar.core.settings import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.app_name == "MustacharAI"
    assert s.app_version == "0.1.0"
    assert s.debug is False
    assert s.log_level == "INFO"
