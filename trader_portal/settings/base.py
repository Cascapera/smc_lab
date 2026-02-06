"""Base Django settings shared across all environments."""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal

import environ
from celery.schedules import crontab

# --------------------------------------------------------------------------------------
# Paths & environment
# --------------------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent
APPS_DIR = BASE_DIR / "trader_portal"

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)

ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    environ.Env.read_env(str(ENV_FILE))

LOG_DIR = Path(env("DJANGO_LOG_DIR", default=str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------
# Core settings
# --------------------------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# --------------------------------------------------------------------------------------
# Applications & middleware
# --------------------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = []

LOCAL_APPS: list[str] = [
    "accounts",
    "trades",
    "macro",
    "payments",
    "discord_integration",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "trader_portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "trader_portal.wsgi.application"
ASGI_APPLICATION = "trader_portal.asgi.application"

# --------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# --------------------------------------------------------------------------------------
# Passwords & authentication
# --------------------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# --------------------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------------------

LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", default="pt-br")
TIME_ZONE = env("DJANGO_TIME_ZONE", default="America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------------------
# Static & media files
# --------------------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS: list[Path] = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SAMESITE = env("DJANGO_CSRF_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_DOMAIN = env("DJANGO_CSRF_COOKIE_DOMAIN", default=None)
SESSION_COOKIE_DOMAIN = env("DJANGO_SESSION_COOKIE_DOMAIN", default=None)
SECURE_PROXY_SSL_HEADER = env.tuple(
    "DJANGO_SECURE_PROXY_SSL_HEADER", default=None
) or None

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "landing"

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = USE_TZ
CELERY_BEAT_SCHEDULE = {
    "macro-collect-every-5min": {
        "task": "macro.tasks.collect_macro_cycle",
        "schedule": crontab(minute="*/5"),  # 00,05,10...
    },
    "discord-sync-daily": {
        "task": "discord_integration.tasks.sync_all_discord_roles",
        "schedule": crontab(minute=0, hour=4),
    },
}

# --------------------------------------------------------------------------------------
# Mercado Pago (pagamentos)
# --------------------------------------------------------------------------------------
MERCADOPAGO_ACCESS_TOKEN = env("MERCADOPAGO_ACCESS_TOKEN", default="")
MERCADOPAGO_PUBLIC_KEY = env("MERCADOPAGO_PUBLIC_KEY", default="")
MERCADOPAGO_CURRENCY = env("MERCADOPAGO_CURRENCY", default="BRL")
MERCADOPAGO_BACK_URL = env("MERCADOPAGO_BACK_URL", default="")
MERCADOPAGO_WEBHOOK_URL = env("MERCADOPAGO_WEBHOOK_URL", default="")
MERCADOPAGO_TEST_PAYER_EMAIL = env("MERCADOPAGO_TEST_PAYER_EMAIL", default="")
MERCADOPAGO_TRIAL_DAYS = env.int("MERCADOPAGO_TRIAL_DAYS", default=7)
MERCADOPAGO_PREMIUM_PLUS_MONTHLY_PRICE = env(
    "MERCADOPAGO_PREMIUM_PLUS_MONTHLY_PRICE", default="250.00"
)
MERCADOPAGO_PREMIUM_PLUS_QUARTERLY_PRICE = env(
    "MERCADOPAGO_PREMIUM_PLUS_QUARTERLY_PRICE", default="600.00"
)
MERCADOPAGO_PREMIUM_PLUS_SEMIANNUAL_PRICE = env(
    "MERCADOPAGO_PREMIUM_PLUS_SEMIANNUAL_PRICE", default="1000.00"
)
MERCADOPAGO_PREMIUM_PLUS_ANNUAL_PRICE = env(
    "MERCADOPAGO_PREMIUM_PLUS_ANNUAL_PRICE", default="1800.00"
)
MERCADOPAGO_PLANS = {
    "basic_monthly": {
        "plan": "basic",
        "label": "Basic Mensal",
        "amount": Decimal(env("MERCADOPAGO_BASIC_MONTHLY_PRICE", default="79.90")),
        "frequency": 1,
        "frequency_type": "months",
        "duration_days": 30,
        "billing_type": "subscription",
    },
    "basic_annual": {
        "plan": "basic",
        "label": "Basic Anual",
        "amount": Decimal(env("MERCADOPAGO_BASIC_ANNUAL_PRICE", default="359.88")),
        "frequency": 12,
        "frequency_type": "months",
        "duration_days": 365,
        "billing_type": "one_time",
    },
    "premium_monthly": {
        "plan": "premium",
        "label": "Premium Mensal",
        "amount": Decimal(env("MERCADOPAGO_PREMIUM_MONTHLY_PRICE", default="129.90")),
        "frequency": 1,
        "frequency_type": "months",
        "duration_days": 30,
        "billing_type": "subscription",
    },
    "premium_annual": {
        "plan": "premium",
        "label": "Premium Anual",
        "amount": Decimal(env("MERCADOPAGO_PREMIUM_ANNUAL_PRICE", default="719.88")),
        "frequency": 12,
        "frequency_type": "months",
        "duration_days": 365,
        "billing_type": "one_time",
    },
    "premium_plus_monthly": {
        "plan": "premium_plus",
        "label": "Premium Plus Mensal",
        "amount": Decimal(env("MERCADOPAGO_PREMIUM_PLUS_MONTHLY_PRICE", default="250.00")),
        "frequency": 1,
        "frequency_type": "months",
        "duration_days": 30,
        "billing_type": "subscription",
    },
    "premium_plus_quarterly": {
        "plan": "premium_plus",
        "label": "Premium Plus Trimestral",
        "amount": Decimal(env("MERCADOPAGO_PREMIUM_PLUS_QUARTERLY_PRICE", default="600.00")),
        "frequency": 3,
        "frequency_type": "months",
        "duration_days": 90,
        "billing_type": "one_time",
    },

    "premium_plus_semiannual": {
        "plan": "premium_plus",
        "label": "Premium Plus Semestral",
        "amount": Decimal(env("MERCADOPAGO_PREMIUM_PLUS_SEMIANNUAL_PRICE", default="1000.00")),
        "frequency": 6,
        "frequency_type": "months",
        "duration_days": 180,
        "billing_type": "one_time",
        
    },
    "premium_plus_annual": {
        "plan": "premium_plus",
        "label": "Premium Plus Anual",
        "amount": Decimal(env("MERCADOPAGO_PREMIUM_PLUS_ANNUAL_PRICE", default="1800.00")),
        "frequency": 12,
        "frequency_type": "months",
        "duration_days": 365,
        "billing_type": "one_time",
        
    },
    "premium_plus_test": {
        "plan": "premium_plus",
        "label": "Premium Plus Teste",
        "amount": Decimal(env("PAGARME_PREMIUM_PLUS_TEST_PRICE", default="5.00")),
        "frequency": 1,
        "frequency_type": "months",
        "duration_days": 30,
        "billing_type": "one_time",
        "provider": "pagarme",
        "hidden": True,
    },
}
MERCADOPAGO_USE_SANDBOX = env.bool("MERCADOPAGO_USE_SANDBOX", default=DEBUG)

# --------------------------------------------------------------------------------------
# Pagar.me
# --------------------------------------------------------------------------------------
PAGARME_SECRET_KEY = env("PAGARME_SECRET_KEY", default="")
PAGARME_PUBLIC_KEY = env("PAGARME_PUBLIC_KEY", default="")
PAGARME_BASE_URL = env("PAGARME_BASE_URL", default="https://api.pagar.me/core/v5")
PAGARME_WEBHOOK_SECRET = env("PAGARME_WEBHOOK_SECRET", default="")
PAGARME_SUCCESS_URL = env("PAGARME_SUCCESS_URL", default="")
PAGARME_FAILURE_URL = env("PAGARME_FAILURE_URL", default="")
PAGARME_WEBHOOK_URL = env("PAGARME_WEBHOOK_URL", default="")
PAGARME_PAYMENT_LINK_URL_BASE = env(
    "PAGARME_PAYMENT_LINK_URL_BASE", default="https://api.pagar.me/checkout/v1/payment-links"
)
PAGARME_PIX_EXPIRES_IN = env.int("PAGARME_PIX_EXPIRES_IN", default=3600)
PAGARME_BOLETO_DAYS = env.int("PAGARME_BOLETO_DAYS", default=3)
PAGARME_BOLETO_INSTRUCTIONS = env(
    "PAGARME_BOLETO_INSTRUCTIONS",
    default="Pagamento referente ao plano SMC Lab.",
)

# --------------------------------------------------------------------------------------
# Discord
# --------------------------------------------------------------------------------------
DISCORD_CLIENT_ID = env("DISCORD_CLIENT_ID", default="")
DISCORD_CLIENT_SECRET = env("DISCORD_CLIENT_SECRET", default="")
DISCORD_REDIRECT_URI = env("DISCORD_REDIRECT_URI", default="")
DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN", default="")
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID", default="")
DISCORD_ROLE_BASIC_ID = env("DISCORD_ROLE_BASIC_ID", default="")
DISCORD_ROLE_PREMIUM_ID = env("DISCORD_ROLE_PREMIUM_ID", default="")
DISCORD_ROLE_PREMIUM_PLUS_ID = env("DISCORD_ROLE_PREMIUM_PLUS_ID", default="")