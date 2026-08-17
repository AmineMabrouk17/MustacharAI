"""Core package — settings, logging, and shared utilities."""

from mustachar.core.logging import setup_logging
from mustachar.core.settings import settings

__all__ = ["settings", "setup_logging"]
