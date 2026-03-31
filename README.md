# SMC Lab — Django SaaS Backend (REST APIs + Celery/Redis + PostgreSQL + Docker + AWS)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)

www.smclab.com.br

---

## 1️⃣ Project Overview

SaaS backend built with Django for recording trading operations, analysis with Smart Money Concepts (SMC), a near–real-time macro dashboard, and Mercado Pago subscriptions. It uses a layered architecture, asynchronous processing with Celery + Redis, a PostgreSQL database, and integration with external APIs (Mercado Pago, Discord, OpenAI). The application is containerized and ready for deployment on AWS Lightsail.

---

## 2️⃣ Key Features

- **Structured trade journal** — Registration with market, timeframe, SMC setup, trigger, P&D, screenshots, and validations
- **AI analysis** — Summaries and insights on the journal via OpenAI GPT-4o mini
- **Macro dashboard** — Automatic collection (every 5 min) of assets from Investing/TradingView via Playwright + BeautifulSoup
- **Payments** — Basic, Premium, and Premium Plus plans with Mercado Pago (subscription and one-off payment)
- **Discord integration** — OAuth2 and role sync by plan (daily sync via Celery Beat)
- **Rate limiting** — Protection on login (5/min) and registration (3/min) per IP
- **Import pipeline** — Management commands to bulk-load trades
- **Analytics dashboard** — Optimized queries with indexes and aggregations

---

## 3️⃣ System Architecture

```
Client (Browser)
    ↓
API Layer (Django Views / Forms)
    ↓
Service Layer (Business rules — services/, llm_service, validators)
    ↓
Data Layer (PostgreSQL — models, ORM)
    ↓
Background Workers (Celery + Redis)
```

**Separation of concerns:**
- **Views** — Receive requests, delegate to services, return responses
- **Services** — Business logic (Mercado Pago, Discord, macro collection, AI analysis)
- **Models** — Persistence and relationships
- **Tasks** — Asynchronous and scheduled jobs

**Decoupling:** External integrations are isolated in `services/` modules (mercadopago, network, collector, parsers).

**Queues:** Celery Beat schedules macro collection (every 5 min) and Discord sync (daily at 4:00). Redis as broker and result backend.

**Modular layout:** Independent Django apps — `accounts`, `trades`, `macro`, `payments`, `discord_integration`.

---

## 4️⃣ Tech Stack

| Layer | Technology |
|--------|------------|
| **Backend** | Python 3.13, Django 5.2 |
| **Database** | PostgreSQL 16 |
| **Async & Background** | Celery 5.3, Redis 7 |
| **Scraping / Automation** | Playwright, BeautifulSoup4, Requests, Pandas |
| **AI** | OpenAI API (gpt-4o-mini) |
| **Payments** | Mercado Pago (SDK/API) |
| **Infrastructure** | Docker, Gunicorn, Whitenoise |
| **CI/CD** | GitHub Actions, Ruff (lint), Pytest/coverage |
| **Deploy** | AWS Lightsail (Docker Compose) |

---

## 5️⃣ API Design

The application is **server-rendered** (Django templates + forms). Main endpoints:

- **Web routes** — `/accounts/`, `/trades/`, `/macro/`, `/pagamentos/`, `/discord/`
- **Webhooks** — `/pagamentos/webhook/` (Mercado Pago) — `csrf_exempt` with HMAC signature validation
- **Response pattern** — HTML for pages; redirects with flash messages for actions
- **Validation** — Django Forms with custom validators (e.g., image size, extensions)
- **Serializers** — No DRF; structured data via forms and `model_to_dict` where needed

---

## 6️⃣ Data Modeling

**Relational modeling:**

- **User / Profile** — 1:1; Profile with plan, balance, Discord, preferences
- **Trade** — N:1 User; SMC fields (setup, trigger, P&D, HTF), financial result, screenshot
- **Payment / Subscription** — N:1 User; indexes on `mp_payment_id`, `external_reference`, `mp_preapproval_id`
- **MacroAsset / MacroVariation / MacroScore** — Macro data collection with `measurement_time` and `unique_together`
- **AIAnalyticsRun / GlobalAIAnalyticsRun** — Log of AI analysis runs

**Indexes:**
- `payments`: `mp_payment_id`, `external_reference`
- `subscriptions`: `mp_preapproval_id`, `external_reference`
- `macro`: `measurement_time`, `status`, `active`, `source_key`
- `Trade`: `ordering` by `-executed_at`, `-id`

**Optimization:** Queries with `select_related`/`prefetch_related` where there are FKs; dashboard aggregations with `annotate` and `values`.

---

## 7️⃣ Asynchronous Processing

**Why Celery:** Macro collection (Playwright) and Discord sync are slow, external operations; they must not block the request.

**Asynchronous tasks:**
- `collect_macro_cycle` — Collects data from Investing/TradingView; runs every 5 min; retry with backoff (up to 3 times)
- `sync_user_roles` — Syncs Discord roles for one user
- `sync_all_discord_roles` — Syncs all profiles; scheduled daily at 4:00

**Retry strategy:** `autoretry_for=(Exception,)`, `retry_backoff=True`, `retry_backoff_max=300`, `max_retries=3`.

**Redis:** Broker and result backend; enables persistence and worker scalability.

---

## 8️⃣ Security & Reliability

- **Authentication** — Django session-based; `LOGIN_REQUIRED` on sensitive views
- **Rate limiting** — `django-ratelimit` on login (5/min) and registration (3/min) per IP
- **CSRF protection** — `CsrfViewMiddleware`; `Secure` and `SameSite=Lax` cookies in production
- **Permission isolation** — `@login_required`; `has_plan_at_least()` checks for plan-gated features
- **Webhooks** — HMAC signature validation for Mercado Pago
- **Error handling** — Structured logging; `RequestTimingMiddleware` for requests >500ms
- **Production** — HSTS, SSL redirect, secure cookies, `ATOMIC_REQUESTS`

---

## 9️⃣ Testing & Code Quality

- **Automated tests** — `manage.py test` with `trader_portal.settings.ci` (in-memory SQLite)
- **Minimum coverage** — 70% (`.coveragerc`); `coverage report --fail-under=70`
- **Linting** — Ruff (`ruff check .`, `ruff format .`); config in `pyproject.toml`
- **Pre-commit (optional)** — Fast local checks before commit: install dev deps with `pip install -r requirements-dev.txt`, then `pre-commit install`. Runs Ruff, Python `check-ast`, and `manage.py check` with `trader_portal.settings.ci` (in-memory SQLite, same as CI). Requires project dependencies installed; does not replace CI.
- **CI** — GitHub Actions: lint + tests + coverage on every push/PR
- **PR workflow** — CI must pass before merge; `makemigrations --check` keeps migrations up to date

---

## 🔟 Running Locally

```bash
# Clone the repository
git clone <repository-url>
cd smc_lab

# Create the .env file
cp .env.example .env
# Edit .env with DATABASE_URL, SECRET_KEY, Redis, etc.

# With Docker (recommended)
docker compose up -d

# Apply migrations (first run)
docker compose exec web python manage.py migrate

# Create superuser (optional)
docker compose exec web python manage.py createsuperuser
```

**App:** http://localhost:8000

### Without Docker

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
# Redis and PostgreSQL running locally

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver

# In another terminal: worker and beat
celery -A trader_portal worker -l info
celery -A trader_portal beat -l info
```

### Environment variables

See `.env.example` for local dev; `docs/env_production_template.txt` for production. Main ones:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_PUBLIC_KEY`, webhook URLs
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`
- `OPENAI_API_KEY`, `OPENAI_ANALYTICS_MODEL`

---

## 1️⃣1️⃣ Deployment

- **Environment** — AWS Lightsail; Docker-enabled instance
- **Docker** — `docker compose` with services: web (Gunicorn), worker, beat, Redis, PostgreSQL
- **Process** — `scripts/deploy.sh`: `git pull` → `docker compose up -d --build` → `migrate` → `collectstatic`
- **CI/CD** — Deploy via GitHub Actions (SSH) after push to `main`; secrets: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`
- **Variables** — `.env` on the server; never committed
- **Worker Watchdog** — Cron script that restarts the Celery worker if it stops; `scripts/install_worker_watchdog.sh`
- **Worker restart** — 3×/day (06:04, 13:04, 22:04) to clear orphan processes; `logs/worker_restart_daily.log`

---

## 1️⃣2️⃣ Future Improvements

- **Observability** — APM (Sentry, DataDog) and distributed tracing
- **Metrics** — Prometheus + Grafana for latency, Celery queues, resource usage
- **Cache layer** — Redis for macro panel and dashboards (heavy query caching)
- **Horizontal scaling** — Multiple Celery workers; Redis as Django cache in production
- **REST APIs** — DRF or FastAPI for integrations and mobile
- **Load testing** — Locust already present; expand scenarios and thresholds

---

## Additional documentation

- **Deploy:** `scripts/deploy.sh` — automated deploy script
- **CI/CD:** `docs/CI_CD_EXPLICACAO.md` — pipeline explanation
- **CD step by step:** `docs/CD_CONFIGURACAO_PASSO_A_PASSO.md`
- **Production env:** `docs/env_production_template.txt`

---

## License

Live project. www.smclab.com.br

