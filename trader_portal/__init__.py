import os

DEFAULT_SETTINGS_MODULE = "trader_portal.settings.dev"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS_MODULE)

from .celery import app as celery_app  # noqa: E402

__all__ = ["DEFAULT_SETTINGS_MODULE", "celery_app"]
