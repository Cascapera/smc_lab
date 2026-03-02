# SMC Lab — Django SaaS Backend (REST APIs + Celery/Redis + PostgreSQL + Docker + AWS)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)

www.smclab.com.br

---

## 1️⃣ Project Overview

Backend SaaS desenvolvido com Django para registro de operações de trading, análise com Smart Money Concepts (SMC), painel macro em tempo quase real e assinaturas com Mercado Pago. Utiliza arquitetura em camadas, processamento assíncrono com Celery + Redis, banco PostgreSQL e integração com APIs externas (Mercado Pago, Discord, OpenAI). Aplicação containerizada e preparada para deploy em AWS Lightsail.

---

## 2️⃣ Key Features

- **Journal de trades estruturado** — Cadastro com mercado, timeframe, setup SMC, trigger, P&D, screenshots e validações
- **Análise por IA** — Resumos e insights sobre o journal via OpenAI GPT-4o mini
- **Painel macro** — Coleta automática (a cada 5 min) de ativos em Investing/TradingView via Playwright + BeautifulSoup
- **Pagamentos** — Planos Basic, Premium e Premium Plus com Mercado Pago (assinatura e pagamento único)
- **Integração Discord** — OAuth2 e sincronização de roles por plano (sync diário via Celery Beat)
- **Rate limiting** — Proteção em login (5/min) e registro (3/min) por IP
- **Pipeline de importação** — Comandos de management para popular trades em lote
- **Dashboard analítico** — Queries otimizadas com índices e agregações

---

## 3️⃣ System Architecture

```
Client (Browser)
    ↓
API Layer (Django Views / Forms)
    ↓
Service Layer (Regras de negócio — services/, llm_service, validators)
    ↓
Data Layer (PostgreSQL — models, ORM)
    ↓
Background Workers (Celery + Redis)
```

**Separação de responsabilidades:**
- **Views** — Recebem requests, delegam para services, retornam respostas
- **Services** — Lógica de negócio (Mercado Pago, Discord, coleta macro, análise IA)
- **Models** — Persistência e relacionamentos
- **Tasks** — Tarefas assíncronas e agendadas

**Desacoplamento:** Integrações externas isoladas em módulos `services/` (mercadopago, network, collector, parsers).

**Filas:** Celery Beat agenda coleta macro (a cada 5 min) e sync Discord (diário às 4h). Redis como broker e result backend.

**Organização modular:** Apps Django independentes — `accounts`, `trades`, `macro`, `payments`, `discord_integration`.

---

## 4️⃣ Tech Stack

| Camada | Tecnologia |
|--------|------------|
| **Backend** | Python 3.13, Django 5.2 |
| **Database** | PostgreSQL 16 |
| **Async & Background** | Celery 5.3, Redis 7 |
| **Scraping / Automação** | Playwright, BeautifulSoup4, Requests, Pandas |
| **IA** | OpenAI API (gpt-4o-mini) |
| **Pagamentos** | Mercado Pago (SDK/API) |
| **Infrastructure** | Docker, Gunicorn, Whitenoise |
| **CI/CD** | GitHub Actions, Ruff (lint), Pytest/coverage |
| **Deploy** | AWS Lightsail (Docker Compose) |

---

## 5️⃣ API Design

A aplicação é **server-rendered** (Django templates + forms). Endpoints principais:

- **Rotas web** — `/accounts/`, `/trades/`, `/macro/`, `/pagamentos/`, `/discord/`
- **Webhooks** — `/pagamentos/webhook/` (Mercado Pago) — `csrf_exempt` com validação de assinatura HMAC
- **Padrão de resposta** — HTML para páginas; redirects com mensagens flash para ações
- **Validações** — Django Forms com validators customizados (ex.: tamanho de imagem, extensões)
- **Serializers** — Não há DRF; dados estruturados via forms e `model_to_dict` onde necessário

---

## 6️⃣ Data Modeling

**Modelagem relacional:**

- **User / Profile** — 1:1; Profile com plano, saldo, Discord, preferências
- **Trade** — N:1 User; campos SMC (setup, trigger, P&D, HTF), resultado financeiro, screenshot
- **Payment / Subscription** — N:1 User; índices em `mp_payment_id`, `external_reference`, `mp_preapproval_id`
- **MacroAsset / MacroVariation / MacroScore** — Coleta de dados macro com `measurement_time` e `unique_together`
- **AIAnalyticsRun / GlobalAIAnalyticsRun** — Registro de execuções de análise por IA

**Índices:**
- `payments`: `mp_payment_id`, `external_reference`
- `subscriptions`: `mp_preapproval_id`, `external_reference`
- `macro`: `measurement_time`, `status`, `active`, `source_key`
- `Trade`: `ordering` por `-executed_at`, `-id`

**Otimização:** Queries com `select_related`/`prefetch_related` onde há FK; agregações no dashboard com `annotate` e `values`.

---

## 7️⃣ Asynchronous Processing

**Por que Celery:** Coleta macro (Playwright) e sync Discord são operações lentas e externas; não podem bloquear o request.

**Tarefas assíncronas:**
- `collect_macro_cycle` — Coleta dados de Investing/TradingView; agenda a cada 5 min; retry com backoff (até 3x)
- `sync_user_roles` — Sincroniza roles Discord de um usuário
- `sync_all_discord_roles` — Sincroniza todos os perfis; agenda diário às 4h

**Estratégia de retry:** `autoretry_for=(Exception,)`, `retry_backoff=True`, `retry_backoff_max=300`, `max_retries=3`.

**Redis:** Broker e result backend; permite persistência e escalabilidade dos workers.

---

## 8️⃣ Security & Reliability

- **Autenticação** — Django session-based; `LOGIN_REQUIRED` em views sensíveis
- **Rate limiting** — `django-ratelimit` em login (5/min) e registro (3/min) por IP
- **Proteção CSRF** — `CsrfViewMiddleware`; cookies `Secure` e `SameSite=Lax` em produção
- **Isolamento de permissões** — `@login_required`; checagem `has_plan_at_least()` para features por plano
- **Webhooks** — Validação de assinatura HMAC no Mercado Pago
- **Tratamento de erros** — Logging estruturado; `RequestTimingMiddleware` para requests >500ms
- **Produção** — HSTS, SSL redirect, cookies seguros, `ATOMIC_REQUESTS`

---

## 9️⃣ Testing & Code Quality

- **Testes automatizados** — `manage.py test` com settings `trader_portal.settings.ci` (SQLite em memória)
- **Cobertura mínima** — 70% (`.coveragerc`); `coverage report --fail-under=70`
- **Linting** — Ruff (`ruff check .`, `ruff format .`); config em `pyproject.toml`
- **CI** — GitHub Actions: lint + testes + cobertura a cada push/PR
- **Fluxo de PR** — CI deve passar antes do merge; `makemigrations --check` garante migrações em dia

---

## 🔟 Running Locally

```bash
# Clone o repositório
git clone <url-do-repositorio>
cd smc_lab

# Crie o arquivo .env
cp .env.example .env
# Edite .env com DATABASE_URL, SECRET_KEY, Redis, etc.

# Com Docker (recomendado)
docker compose up -d

# Aplicar migrações (primeira vez)
docker compose exec web python manage.py migrate

# Criar superusuário (opcional)
docker compose exec web python manage.py createsuperuser
```

**Aplicação:** http://localhost:8000

### Sem Docker

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
# Redis e PostgreSQL rodando localmente

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver

# Em outro terminal: worker e beat
celery -A trader_portal worker -l info
celery -A trader_portal beat -l info
```

### Variáveis de ambiente

Consulte `.env.example` para dev local; `docs/env_production_template.txt` para produção. Principais:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_PUBLIC_KEY`, URLs de webhook
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`
- `OPENAI_API_KEY`, `OPENAI_ANALYTICS_MODEL`

---

## 1️⃣1️⃣ Deployment

- **Ambiente** — AWS Lightsail; instância com Docker
- **Docker** — `docker compose` com serviços: web (Gunicorn), worker, beat, Redis, PostgreSQL
- **Processo** — `scripts/deploy.sh`: `git pull` → `docker compose up -d --build` → `migrate` → `collectstatic`
- **CI/CD** — Deploy via GitHub Actions (SSH) após push na `main`; secrets: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`
- **Variáveis** — `.env` no servidor; nunca commitado
- **Worker Watchdog** — Script cron que reinicia Celery worker se parar; `scripts/install_worker_watchdog.sh`
- **Reinício do worker** — 3x/dia (06:04, 13:04, 22:04) para limpar processos órfãos; `logs/worker_restart_daily.log`

---

## 1️⃣2️⃣ Future Improvements

- **Observabilidade** — APM (Sentry, DataDog) e tracing distribuído
- **Métricas** — Prometheus + Grafana para latência, filas Celery, uso de recursos
- **Cache layer** — Redis para painel macro e dashboards (cache de queries pesadas)
- **Escalabilidade horizontal** — Múltiplos workers Celery; Redis como cache Django em produção
- **APIs REST** — DRF ou FastAPI para integrações e mobile
- **Testes de carga** — Locust já presente; expandir cenários e thresholds

---

## Documentação adicional

- **Deploy:** `scripts/deploy.sh` — script de deploy automatizado
- **CI/CD:** `docs/CI_CD_EXPLICACAO.md` — explicação do pipeline
- **CD passo a passo:** `docs/CD_CONFIGURACAO_PASSO_A_PASSO.md`
- **Env produção:** `docs/env_production_template.txt`

---

## Licença

Projeto em execução. www.smclab.com.br

