"""Development settings."""

from __future__ import annotations

from .base import *  # noqa

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# Dev local sem Docker: USE_SQLITE_LOCAL=true usa SQLite em vez de PostgreSQL
if env.bool("USE_SQLITE_LOCAL", default=False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "ATOMIC_REQUESTS": True,
        }
    }
else:
    # Host "postgres" só resolve dentro do Docker. Para migrate/runserver no host,
    # defina DATABASE_HOST=localhost (e DATABASE_PORT se houver conflito na 5432).
    db_host = env("DATABASE_HOST", default=None)
    db_port = env("DATABASE_PORT", default=None)
    if db_host:
        DATABASES["default"]["HOST"] = db_host
    if db_port:
        DATABASES["default"]["PORT"] = str(db_port)

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-secret-key",
)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

# Debug Toolbar: painel lateral com queries SQL e tempo de request.
#
# O import é condicional porque `django-debug-toolbar` saiu do
# `requirements.txt` (ia junto para a imagem de produção) e agora só está no
# `requirements-dev.txt`. Quem rodar dev com as dependências de produção
# continua funcionando, sem o painel.
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1", "localhost"]
    MIDDLEWARE = [
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ] + MIDDLEWARE  # noqa: F405
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
    }
except ImportError:  # pragma: no cover - só acontece fora do ambiente de dev
    pass

# Mesmos loggers JSON do macro que em produção (merge sobre o DEFAULT_LOGGING do Django)
from django.utils.log import DEFAULT_LOGGING  # noqa: E402

LOGGING = merge_macro_into_logging(DEFAULT_LOGGING)  # noqa: F405
