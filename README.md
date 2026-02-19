# SMC Lab — Portal para Traders
www.smclab.com.br

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)

**Plataforma SaaS** para registro de operações, análise com **Smart Money Concepts (SMC)**, painel macro em tempo quase real, assinaturas com **Mercado Pago** e integração com **Discord**. Inclui análise de trades com **IA (OpenAI GPT)** e automação de coleta de dados com **Playwright**.

---

## Destaques do projeto

- **Journal de trades** — Cadastro estruturado (mercado, timeframe, setup SMC, trigger, P&D, screenshots)
- **Análise por IA** — Resumos e insights sobre o journal usando GPT-4o mini
- **Painel macro** — Coleta automática (a cada 5 min) de ativos em Investing/TradingView via scraping + Playwright
- **Pagamentos** — Planos Basic, Premium e Premium Plus com Mercado Pago (assinatura e pagamento único)
- **Discord** — Sincronização de roles por plano (sync diário via Celery Beat)
- **Deploy** — Docker Compose (web, worker, beat, Redis, PostgreSQL), pronto para produção com Gunicorn e Whitenoise

---

## Stack tecnológica

| Camada | Tecnologia |
|--------|------------|
| Backend | Django 5.2, Python 3.13 |
| Banco de dados | PostgreSQL 16 |
| Filas e tarefas | Celery 5.3, Redis |
| Scraping / automação | Playwright, BeautifulSoup4, Requests, Pandas |
| IA | OpenAI API (gpt-4o-mini) |
| Pagamentos | Mercado Pago (SDK/API) |
| Infraestrutura | Docker, Gunicorn, Whitenoise |

---

## Pré-requisitos

- **Python 3.13**
- **PostgreSQL 16** (ou uso via Docker)
- **Redis** (broker e backend do Celery)
- Contas/credenciais (conforme uso): Mercado Pago, Discord (OAuth2 + Bot), OpenAI

---

## Como rodar o projeto

### Com Docker (recomendado)

```bash
# Clone o repositório
git clone <url-do-repositorio>
cd smc_lab

# Crie o arquivo .env (veja docs/env_production_template.txt ou .env.example)
cp docs/env_production_template.txt .env
# Edite .env com DATABASE_URL, SECRET_KEY, Redis, etc.

# Sobe todos os serviços
docker compose up -d

# Aplicar migrações (primeira vez)
docker compose exec web python manage.py migrate

# Criar superusuário (opcional)
docker compose exec web python manage.py createsuperuser
```

Aplicação: **http://localhost:8000**

### Sem Docker (ambiente local)

```bash
# Ambiente virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

# Dependências
pip install -r requirements.txt

# Variáveis de ambiente no .env (DATABASE_URL, CELERY_BROKER_URL, etc.)
# Redis e PostgreSQL devem estar rodando localmente

# Migrações
python manage.py migrate

# Coletar estáticos
python manage.py collectstatic --noinput

# Servidor (dev)
python manage.py runserver

# Em outro terminal: worker e beat
celery -A trader_portal worker -l info
celery -A trader_portal beat -l info
```

---

## Estrutura principal do código

```
smc_lab/
├── accounts/          # Usuários, perfis, planos, login/registro
├── trades/             # Journal de trades, dashboards, análise com IA
├── macro/              # Ativos macro, coleta (Playwright), painel SMC
├── payments/           # Planos, assinaturas, integração Mercado Pago
├── discord_integration/# OAuth2 Discord, sync de roles por plano
├── trader_portal/      # Projeto Django (settings, urls, celery, wsgi)
├── templates/          # Base, landing, partials
├── static/             # CSS, JS, imagens
├── docs/               # Deploy, cheatsheets, templates de env
├── scripts/            # Backup, deploy, setup (ex.: Lightsail)
├── docker-compose.yml
├── Dockerfile          # Playwright + Python 3 (coleta macro)
└── requirements.txt
```

---

## Variáveis de ambiente (resumo)

As configurações são carregadas via `django-environ` a partir de um arquivo `.env`. Principais variáveis:

- **Django:** `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`
- **Celery:** `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- **Mercado Pago:** `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_PUBLIC_KEY`, URLs de retorno/webhook, preços por plano
- **Discord:** `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, IDs das roles
- **OpenAI:** `OPENAI_API_KEY`, `OPENAI_ANALYTICS_MODEL`

Consulte `docs/env_production_template.txt` para um template completo.

---

## Documentação adicional

- **Deploy:** `docs/deploy_lightsail.md`
- **Docker:** `docs/docker_cheatsheet.txt`
- **SSH/Deploy:** `docs/ssh_deploy_cheatsheet.txt`
- **Env produção:** `docs/env_production_template.txt`

---

## Licença

Projeto real em execução.
www.smclab.com.br

---