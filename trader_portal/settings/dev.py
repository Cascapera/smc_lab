"""Development settings."""

from __future__ import annotations

from .base import *  # noqa

DEBUG = env.bool("DJANGO_DEBUG", default=True)

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-secret-key",
)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405

INTERNAL_IPS = ["127.0.0.1", "localhost"]

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE  # noqa: F405

# Debug Toolbar: mostra painel lateral com queries SQL e tempo de request
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}

