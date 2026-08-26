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
# browser buscar o arquivo novo depois de cada deploy. O manifest e gerado no
# build da imagem (o Dockerfile falha se ele nao sair).
#
# Usamos a subclasse resiliente, e nao a do whitenoise direto: com
# `manifest_strict = True` (o padrao), uma entrada ausente levanta ValueError e
# derruba a pagina inteira. Ja aconteceu: o site ficou 500 por completo.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "trader_portal.storage.ResilientManifestStaticFilesStorage",
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

# `macro_file` só entra se der para escrever no LOG_DIR (ver I19 no base.py).
# Sem isso, um LOG_DIR não gravável faz o dictConfig estourar na inicialização
# do processo — o site inteiro fora por causa de um arquivo de log secundário.
_aplicar_macro_file = add_macro_file_handler if LOG_DIR_GRAVAVEL else (lambda cfg: cfg)  # noqa: F405

LOGGING = _aplicar_macro_file(
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
                **(
                    {
                        "macro_file": {
                            "class": "logging.handlers.RotatingFileHandler",
                            "formatter": "verbose",
                            "filename": str(LOG_DIR / "macro_errors.log"),  # noqa: F405
                            "maxBytes": 5 * 1024 * 1024,
                            "backupCount": 5,
                            "level": "ERROR",
                        }
                    }
                    if LOG_DIR_GRAVAVEL  # noqa: F405
                    else {}
                ),
            },
            "root": {
                "handlers": ["console"],
                "level": env("DJANGO_LOG_LEVEL", default="INFO"),  # noqa: F405
            },
            "loggers": {
                "macro": {
                    "handlers": ["console", "macro_file"] if LOG_DIR_GRAVAVEL else ["console"],  # noqa: F405
                    "level": env("MACRO_LOG_LEVEL", default="INFO"),  # noqa: F405
                    "propagate": False,
                }
            },
        }
    )
)


# --------------------------------------------------------------------------------------
# Sentry (opcional)
# --------------------------------------------------------------------------------------
# Liga sozinho quando `SENTRY_DSN` aparecer no .env e os containers reiniciarem —
# não precisa de deploy de código. Sem DSN, nada é inicializado: nenhuma
# requisição de rede, nenhum hook, nenhum custo.
#
# `send_default_pii=False` é deliberado: o Sentry captura corpo de requisição e
# dados de usuário quando ligado, e aqui trafegam e-mail, documento e telefone
# de cliente. O que interessa para depurar é o stack trace.
SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            # Sem esta, erro dentro de task do Celery não chega ao Sentry — e é
            # justamente onde ninguém está olhando quando acontece.
            CeleryIntegration(),
            LoggingIntegration(level=None, event_level="ERROR"),
        ],
        environment=env("SENTRY_ENVIRONMENT", default="production"),  # noqa: F405
        release=env("GIT_SHA", default=""),  # noqa: F405
        # Amostragem de performance desligada: o plano gratuito é pequeno e o
        # que interessa agora é erro, não traço.
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
