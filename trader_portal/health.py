"""
Endpoint de saúde para monitor externo.

Existe por causa de uma lição específica: durante um deploy o site respondeu
HTTP 200 o tempo todo enquanto a coleta macro estava completamente parada. A
página inicial responder não prova que o sistema funciona — prova que o gunicorn
está de pé.

O que este endpoint pergunta:

- **banco**: `SELECT 1` de verdade, não `connection.ensure_connection()`, que
  pode reusar uma conexão morta com `CONN_MAX_AGE` ligado
- **cache**: ida e volta no Redis. Um `set` sozinho não serve: o
  `ResilientRedisCache` engole a falha de propósito (para não derrubar o login)
  e devolveria "ok" com o Redis fora. Só o `get` trazendo o valor de volta prova
  que o Redis respondeu
- **coleta**: idade do último `MacroScore`. É o dado que o usuário vê no painel,
  e vem do banco — se o Redis cair, esta parte continua respondendo

A coleta só é considerada atrasada com o **mercado aberto**. Sem isso o monitor
apitaria toda madrugada, e um alerta que toca sem motivo é um alerta que
ninguém lê.
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)

# Um ciclo é agendado a cada 5 min e leva ~90s. 30 min = seis agendamentos
# seguidos sem dado novo: aí é problema, não lentidão.
MAX_IDADE_COLETA_MINUTOS = 30

_CHAVE_DE_TESTE = "healthz:ping"


def _checar_banco() -> tuple[bool, str]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        logger.error("[healthz] Banco indisponível: %s", exc, exc_info=True)
        return False, f"erro: {type(exc).__name__}"
    return True, "ok"


def _checar_cache() -> tuple[bool, str]:
    marca = timezone.now().isoformat()
    try:
        cache.set(_CHAVE_DE_TESTE, marca, 30)
        devolvido = cache.get(_CHAVE_DE_TESTE)
    except Exception as exc:
        logger.error("[healthz] Cache indisponível: %s", exc, exc_info=True)
        return False, f"erro: {type(exc).__name__}"

    if devolvido != marca:
        # Caminho do ResilientRedisCache degradado: não levanta, devolve None.
        return False, "sem resposta do redis"
    return True, "ok"


def _checar_coleta() -> tuple[bool, dict]:
    from macro.models import MacroScore
    from macro.services.utils import is_market_closed

    try:
        ultimo = MacroScore.objects.order_by("-measurement_time").first()
    except Exception as exc:
        logger.error("[healthz] Falha ao ler o último ciclo: %s", exc, exc_info=True)
        return False, {"status": f"erro: {type(exc).__name__}"}

    if ultimo is None:
        return False, {"status": "nenhum ciclo registrado"}

    idade_minutos = int((timezone.now() - ultimo.measurement_time).total_seconds() // 60)
    mercado_fechado = is_market_closed()
    detalhe = {
        "idade_minutos": idade_minutos,
        "mercado_fechado": mercado_fechado,
        "ultimo_ciclo": ultimo.measurement_time.isoformat(),
    }

    if mercado_fechado:
        detalhe["status"] = "ok (mercado fechado)"
        return True, detalhe

    if idade_minutos > MAX_IDADE_COLETA_MINUTOS:
        detalhe["status"] = f"atrasado (limite {MAX_IDADE_COLETA_MINUTOS} min)"
        return False, detalhe

    detalhe["status"] = "ok"
    return True, detalhe


@never_cache
def healthz(request):
    """Saúde do sistema, não da página. 200 = saudável, 503 = alguém precisa olhar."""
    banco_ok, banco_detalhe = _checar_banco()
    cache_ok, cache_detalhe = _checar_cache()
    coleta_ok, coleta_detalhe = _checar_coleta()

    saudavel = banco_ok and cache_ok and coleta_ok
    corpo = {
        "status": "ok" if saudavel else "degradado",
        "checks": {
            "banco": banco_detalhe,
            "cache": cache_detalhe,
            "coleta": coleta_detalhe,
        },
    }
    return JsonResponse(corpo, status=200 if saudavel else 503)
