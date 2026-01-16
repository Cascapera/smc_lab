"""
Settings package initializer.

The actual settings module is selected via the `DJANGO_SETTINGS_MODULE`
environment variable. For local management commands we default to the
development configuration (`trader_portal.settings.dev`), while
production entrypoints explicitly point to `trader_portal.settings.prod`.
"""

from __future__ import annotations

import os

DEFAULT_SETTINGS_MODULE = "trader_portal.settings.dev"

# Do not override if the variable is already defined externally.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS_MODULE)

__all__ = ["DEFAULT_SETTINGS_MODULE"]

