# CI/CD — SMC Lab

**CI** roda a cada push/PR. **CD** faz deploy no Lightsail após push na `main`.

---

## Workflows

| Arquivo | Gatilho | Função |
|---------|---------|--------|
| `.github/workflows/ci.yml` | push, pull_request | Lint (Ruff) + testes + cobertura |
| `.github/workflows/deploy.yml` | workflow_dispatch (ou push na main) | Deploy via SSH |

---

## CI — O que roda

1. **Lint:** `ruff check .` e `ruff format --check`
2. **Testes:** `manage.py check` → `makemigrations --check` → `manage.py test`
3. **Cobertura:** mínimo 70% (`.coveragerc`)

Settings: `trader_portal.settings.ci` (SQLite em memória, sem Redis/PostgreSQL).

---

## Rodar localmente

```bash
# Lint
pip install ruff
ruff check .
ruff format .

# Testes
pip install -r requirements-dev.txt
coverage run manage.py test --settings=trader_portal.settings.ci
coverage report --fail-under=70

# Relatório HTML
coverage html
```

---

## CD — Configuração

**GitHub Secrets:** `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `DEPLOY_PATH` (opcional)

**Servidor:** repo clonado, `.env` configurado, chave pública em `~/.ssh/authorized_keys`

**Fluxo:** `git pull` → `docker compose build` → `docker compose up -d` → `migrate` → `collectstatic`

Detalhes: `docs/CD_CONFIGURACAO_PASSO_A_PASSO.md`
