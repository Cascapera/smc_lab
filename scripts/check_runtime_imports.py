"""
Importa os módulos carregados na inicialização do worker, do gunicorn e das
migrações — na versão de Python que for executar este script.

Por que existe: o CI roda em 3.13 e a imagem de produção em 3.10 (Ubuntu
22.04). Código com sintaxe ou símbolos de 3.11+ passa por toda a suíte e só
quebra no servidor. Aconteceu com `from datetime import UTC`: o worker entrou em
loop de restart enquanto o site seguia respondendo 200, escondendo a falha.

Por que num arquivo, e não repetido em dois lugares: a lista estava duplicada no
`Dockerfile` e no `ci.yml`, e as duas versões já tinham divergido — a do CI não
importava `accounts.views` nem `accounts.discord_links`. Uma lista só não tem
como divergir de si mesma.

Uso:
    DJANGO_SETTINGS_MODULE=... python scripts/check_runtime_imports.py
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

# Rodado como `python scripts/check_runtime_imports.py`, o sys.path[0] é
# `scripts/` — a raiz do projeto não entra sozinha e `import trader_portal`
# falha antes de qualquer verificação acontecer.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Módulos que o processo carrega antes de servir a primeira requisição ou
# consumir a primeira tarefa. Se algum não importar, o processo não sobe.
MODULOS = [
    # worker
    "macro.tasks",
    "macro.services.network",
    "macro.services.collector",
    "macro.services.retention",
    "trades.tasks",
    "trades.services.analytics_ia",
    "accounts.tasks",
    "discord_integration.tasks",
    # web (gunicorn)
    "accounts.views",
    "trader_portal.health",
    "trader_portal.urls",
    # migrações e serviços de pagamento
    "accounts.discord_links",
    "payments.services.plans",
    "payments.services.mercadopago",
]


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trader_portal.settings.ci")

    import django

    django.setup()

    falhas = []
    for modulo in MODULOS:
        try:
            importlib.import_module(modulo)
        except Exception as exc:  # noqa: BLE001 - queremos reportar todas de uma vez
            falhas.append((modulo, f"{type(exc).__name__}: {exc}"))

    if falhas:
        print(f"FALHA: {len(falhas)} módulo(s) não importam em {sys.version.split()[0]}:")
        for modulo, erro in falhas:
            print(f"  - {modulo}: {erro}")
        return 1

    print(f"imports de runtime: ok em {sys.version.split()[0]} ({len(MODULOS)} módulos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
