"""
Configurações para CI (GitHub Actions e outros pipelines).

Usa SQLite em memória para testes rápidos, sem PostgreSQL/Redis.
"""

from __future__ import annotations

from .base import *  # noqa: F401, F403

DEBUG = False
SECRET_KEY = "ci-secret-key-not-for-production"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# SQLite em memória: mais rápido e não deixa arquivos
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "ATOMIC_REQUESTS": True,
    }
}

# Desabilita integrações externas durante testes
CELERY_TASK_ALWAYS_EAGER = True  # Executa tasks síncronamente (sem Redis)
CELERY_TASK_EAGER_PROPAGATION = True

# Cache em memória (sem Redis)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ci-cache",
    }
}

# Hasher rápido para testes (evita lentidão do PBKDF2)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
