"""
Backend de cache que degrada em vez de derrubar a requisição.

Motivo: ao mover o cache do LocMemCache para o Redis (para o rate limit valer
entre os workers do gunicorn, e não por processo), o Redis passa a estar no
caminho do login. Com o `RedisCache` padrão do Django, um Redis indisponível
levanta `ConnectionError` dentro do decorator de rate limit e o POST de login
responde 500 — verificado.

O cache aqui é usado para *proteções* (rate limit de login/registro, trava do
ciclo de coleta macro), não como fonte de verdade. A degradação correta é
desligar a proteção e manter o site funcionando, não recusar o login.

Consequência assumida: enquanto o Redis estiver fora, não há rate limit e dois
ciclos de coleta poderiam se sobrepor. As duas coisas são preferíveis a usuários
sem conseguir entrar. As falhas são logadas em ERROR para não passarem
despercebidas.
"""

from __future__ import annotations

import logging
from functools import wraps

from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)


def _erros_de_conexao() -> tuple[type[BaseException], ...]:
    """Erros do redis-py mais os de socket, sem quebrar se a lib mudar."""
    erros: list[type[BaseException]] = [OSError]
    try:
        from redis.exceptions import RedisError

        erros.append(RedisError)
    except Exception:  # pragma: no cover - redis sempre presente em produção
        pass
    return tuple(erros)


ERROS_DE_CACHE = _erros_de_conexao()


def _degrada(retorno_em_falha):
    """Executa a operação; se o cache estiver fora, loga e devolve o fallback."""

    def decorador(metodo):
        @wraps(metodo)
        def wrapper(self, *args, **kwargs):
            try:
                return metodo(self, *args, **kwargs)
            except ERROS_DE_CACHE as exc:
                logger.error(
                    "[cache] Redis indisponível em %s(); seguindo sem cache: %s",
                    metodo.__name__,
                    exc,
                )
                return retorno_em_falha
            except Exception as exc:  # noqa: BLE001 - cache nunca deve derrubar a request
                logger.exception("[cache] Erro inesperado em %s(): %s", metodo.__name__, exc)
                return retorno_em_falha

        return wrapper

    return decorador


class ResilientRedisCache(RedisCache):
    """RedisCache que nunca propaga erro de conexão para a view."""

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default, version)
        except ERROS_DE_CACHE as exc:
            logger.error("[cache] Redis indisponível em get(); seguindo sem cache: %s", exc)
            return default
        except Exception as exc:  # noqa: BLE001
            logger.exception("[cache] Erro inesperado em get(): %s", exc)
            return default

    # `add` retornando True significa "consegui a trava". É a degradação certa:
    # sem Redis, o ciclo de coleta roda (melhor do que parar de coletar) e o
    # rate limit trata a requisição como a primeira da janela (fail-open).
    add = _degrada(True)(RedisCache.add)

    # `incr` é o que o django-ratelimit usa para contar. Devolver 1 equivale a
    # "primeira requisição da janela", ou seja, não bloqueia ninguém.
    incr = _degrada(1)(RedisCache.incr)

    set = _degrada(None)(RedisCache.set)
    delete = _degrada(False)(RedisCache.delete)
    touch = _degrada(False)(RedisCache.touch)
    has_key = _degrada(False)(RedisCache.has_key)
    get_many = _degrada({})(RedisCache.get_many)
    set_many = _degrada([])(RedisCache.set_many)
    delete_many = _degrada(None)(RedisCache.delete_many)
    clear = _degrada(None)(RedisCache.clear)
