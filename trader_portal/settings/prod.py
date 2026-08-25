"""Production settings."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY", default=None)
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must include at least one host.")

DATABASES["default"] = env.db("DATABASE_URL", default=None)
if not DATABASES["default"]:
    raise ImproperlyConfigured("DATABASE_URL must be set in production.")
DATABASES["default"]["ATOMIC_REQUESTS"] = True

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# WhiteNoise com manifest: comprime e adiciona hash ao nome do arquivo, para o
# browser buscar o arquivo novo depois de cada deploy. Exige `collectstatic`,
# que o Dockerfile e o passo de deploy já executam.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Cache no Redis (o mesmo já usado como broker do Celery).
#
# Com o LocMemCache do base.py, cada worker do gunicorn tinha seu próprio cache:
# o rate limit de login (5/min) e de registro (3/min) valia por processo, ou
# seja, o limite real era o dobro, e zerava a cada restart. A trava de ciclo da
# coleta macro tem o mesmo problema quando houver mais de um processo.
# Usamos o ResilientRedisCache, e não o RedisCache padrão: com o cache no
# caminho do login, um Redis indisponível faria o rate limit levantar
# ConnectionError e o POST de login responder 500. O backend resiliente desliga
# a proteção e mantém o site de pé, logando o erro.
CACHES = {
    "default": {
        "BACKEND": "trader_portal.cache.ResilientRedisCache",
        "LOCATION": env("DJANGO_CACHE_URL", default="redis://redis:6379/1"),
    }
}

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)

# Middleware de timing para identificar requests lentos (>500ms)
MIDDLEWARE = [
    "trader_portal.middleware.RequestTimingMiddleware",
] + MIDDLEWARE  # noqa: F405

LOGGING = add_macro_file_handler(  # noqa: F405
    merge_macro_into_logging(  # noqa: F405
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "verbose": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "verbose",
                },
                "macro_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "verbose",
                    "filename": str(LOG_DIR / "macro_errors.log"),  # noqa: F405
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "level": "ERROR",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": env("DJANGO_LOG_LEVEL", default="INFO"),  # noqa: F405
            },
            "loggers": {
                "macro": {
                    "handlers": ["console", "macro_file"],
                    "level": env("MACRO_LOG_LEVEL", default="INFO"),  # noqa: F405
                    "propagate": False,
                }
            },
        }
    )
)
