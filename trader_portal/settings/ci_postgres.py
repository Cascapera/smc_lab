"""
Settings de teste contra PostgreSQL.

O CI roda em SQLite em memória (`settings.ci`): é rápido, mas esconde diferenças
reais do banco de produção — constraints parciais (`UniqueConstraint` com
`condition`), `select_for_update`, precisão de `Decimal`, ordenação e timezone.

Use este módulo para validar migrações e concorrência antes de subir para
produção:

    docker run -d --name smc_pg_test -p 55432:5432 \\
      -e POSTGRES_USER=testuser -e POSTGRES_PASSWORD=testpass \\
      -e POSTGRES_DB=testdb postgres:16-alpine

    DATABASE_URL=postgres://testuser:testpass@localhost:55432/testdb \\
      python manage.py test --settings=trader_portal.settings.ci_postgres

Não é usado em produção: serve só para teste.
"""

from __future__ import annotations

from .ci import *  # noqa: F401,F403

DATABASES = {
    "default": env.db("DATABASE_URL"),  # noqa: F405
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
