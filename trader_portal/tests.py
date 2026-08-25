"""
Testes do backend de cache resiliente.

Contexto: ao mover o cache para o Redis (para o rate limit valer entre os
workers do gunicorn, e não por processo), o Redis entrou no caminho do login.
Com o `RedisCache` padrão, um Redis fora do ar levanta `ConnectionError` dentro
do decorator de rate limit e o POST de login responde 500.
"""

from __future__ import annotations

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

# Porta sem nada escutando: simula o Redis indisponível.
CACHE_MORTO = {
    "default": {
        "BACKEND": "trader_portal.cache.ResilientRedisCache",
        "LOCATION": "redis://127.0.0.1:6399/0",
        "OPTIONS": {"socket_connect_timeout": 0.2, "socket_timeout": 0.2},
    }
}


@override_settings(CACHES=CACHE_MORTO)
class ResilientRedisCacheTest(SimpleTestCase):
    """Com o Redis fora, nenhuma operação pode propagar exceção."""

    def setUp(self):
        caches.close_all()
        self.cache = caches.create_connection("default")

    def test_set_nao_levanta(self):
        self.assertIsNone(self.cache.set("chave", "valor", 30))

    def test_get_devolve_o_default(self):
        self.assertEqual(self.cache.get("chave", "padrao"), "padrao")

    def test_get_sem_default_devolve_none(self):
        self.assertIsNone(self.cache.get("chave"))

    def test_add_faz_fail_open(self):
        """
        `add` é a trava do ciclo de coleta macro. Devolver True significa
        "consegui a trava": sem Redis, é melhor coletar do que parar de coletar.
        """
        self.assertTrue(self.cache.add("macro:cycle_lock", "1", 60))

    def test_incr_faz_fail_open(self):
        """
        `incr` é o que o django-ratelimit usa para contar. Devolver 1 equivale a
        "primeira requisição da janela", então ninguém é bloqueado.
        """
        self.assertEqual(self.cache.incr("rate:login:1.2.3.4"), 1)

    def test_delete_e_has_key_nao_levantam(self):
        self.assertFalse(self.cache.delete("chave"))
        self.assertFalse(self.cache.has_key("chave"))

    def test_get_many_e_set_many_nao_levantam(self):
        self.assertEqual(self.cache.get_many(["a", "b"]), {})
        self.assertEqual(self.cache.set_many({"a": 1}), [])

    def test_ciclo_completo_de_login_nao_quebra(self):
        """Sequência que o django-ratelimit executa num POST de login."""
        chave = "rate:login:ip"
        self.assertTrue(self.cache.add(chave, 1, 60))
        self.assertEqual(self.cache.incr(chave), 1)
        self.assertIsNone(self.cache.get(chave))
