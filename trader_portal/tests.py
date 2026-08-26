"""
Testes do backend de cache resiliente.

Contexto: ao mover o cache para o Redis (para o rate limit valer entre os
workers do gunicorn, e não por processo), o Redis entrou no caminho do login.
Com o `RedisCache` padrão, um Redis fora do ar levanta `ConnectionError` dentro
do decorator de rate limit e o POST de login responde 500.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from trader_portal.settings import base as base_settings

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


# ---------------------------------------------------------------------------
# Storage de estáticos resiliente
# ---------------------------------------------------------------------------


class ResilientManifestStorageTest(SimpleTestCase):
    """
    Regressão do incidente: ligar o storage de manifest tirou o site do ar.

    A imagem Docker saía sem `staticfiles.json` (o collectstatic do Dockerfile
    rodava com settings de dev), o container subia com settings de produção, o
    storage carregava zero entradas e todo `{% static %}` levantava ValueError —
    500 em todas as páginas.
    """

    def _storage(self):
        from trader_portal.storage import ResilientManifestStaticFilesStorage

        return ResilientManifestStaticFilesStorage()

    def test_manifest_nao_e_estrito(self):
        """`manifest_strict=True` é o que transforma entrada ausente em 500."""
        self.assertFalse(self._storage().manifest_strict)

    def test_manifest_vazio_nao_levanta(self):
        """Cenário exato do incidente: processo subiu sem manifest."""
        storage = self._storage()
        storage.hashed_files = {}
        try:
            resultado = storage.stored_name("image/logo.png")
        except Exception as exc:  # pragma: no cover
            self.fail(f"stored_name levantou {type(exc).__name__}: {exc}")
        self.assertTrue(resultado)

    def test_arquivo_inexistente_devolve_o_caminho_original(self):
        """Pior caso: nem o arquivo existe. Ainda assim a página deve renderizar."""
        storage = self._storage()
        storage.hashed_files = {}
        self.assertEqual(
            storage.stored_name("nao/existe/em/lugar/nenhum.css"),
            "nao/existe/em/lugar/nenhum.css",
        )

    def test_usa_o_manifest_quando_ele_existe(self):
        storage = self._storage()
        storage.hashed_files = {"image/logo.png": "image/logo.abc123.png"}
        self.assertEqual(storage.stored_name("image/logo.png"), "image/logo.abc123.png")


# ---------------------------------------------------------------------------
# Settings do Celery que existem de verdade (I12)
# ---------------------------------------------------------------------------


class SettingsDoCeleryTest(SimpleTestCase):
    """
    Regressão de I12.

    `CELERY_WORKER_GRACEFUL_TIMEOUT` não existe no Celery e ficou anos no
    settings com um comentário afirmando que o worker esperava 5 minutos por
    tarefa — não esperava. `CELERY_TASK_EAGER_PROPAGATION` (sem o S) era outro
    nome inexistente, e esse tinha efeito colateral: exceção dentro de uma task
    ficava presa no `EagerResult` e o teste passava com a task quebrada.

    Este teste não confere dois nomes: confere *todos*, para que o próximo typo
    apareça aqui e não em produção.
    """

    def test_toda_chave_celery_existe_no_celery(self):
        from celery.app import defaults

        desconhecidas = []
        for nome in dir(settings):
            if not nome.startswith("CELERY_"):
                continue
            opcao = nome[len("CELERY_") :].lower()
            try:
                defaults.find(opcao)
            except KeyError:
                # `find` levanta KeyError para nome inexistente, não devolve None.
                desconhecidas.append(nome)

        self.assertEqual(desconhecidas, [], f"Settings inexistentes no Celery: {desconhecidas}")

    def test_eager_propagates_esta_escrito_certo(self):
        """O nome com S é o que faz a exceção da task chegar ao teste."""
        self.assertTrue(settings.CELERY_TASK_EAGER_PROPAGATES)
        self.assertFalse(hasattr(settings, "CELERY_TASK_EAGER_PROPAGATION"))

    def test_espera_do_worker_vem_do_compose_e_nao_do_settings(self):
        self.assertFalse(hasattr(settings, "CELERY_WORKER_GRACEFUL_TIMEOUT"))


# ---------------------------------------------------------------------------
# Rate limit explícito, não derivado de sys.argv (I18)
# ---------------------------------------------------------------------------


class RateLimitEnableTest(SimpleTestCase):
    """
    Regressão de I18.

    Era `RATELIMIT_ENABLE = "test" not in sys.argv`: qualquer comando com a
    palavra `test` num argumento desligava a proteção — `manage.py loaddata
    test.json`, por exemplo. E, como a suíte sempre caía nessa condição, o rate
    limit nunca era exercitado por teste nenhum.
    """

    def test_desligado_explicitamente_na_suite(self):
        self.assertFalse(settings.RATELIMIT_ENABLE)

    def test_base_nao_olha_para_a_linha_de_comando(self):
        fonte = (Path(settings.BASE_DIR) / "trader_portal" / "settings" / "base.py").read_text(
            encoding="utf-8"
        )
        linha_do_setting = [
            linha
            for linha in fonte.splitlines()
            if linha.startswith("RATELIMIT_ENABLE") and "=" in linha
        ]
        self.assertEqual(len(linha_do_setting), 1)
        self.assertNotIn("sys.argv", linha_do_setting[0])


# ---------------------------------------------------------------------------
# LOG_DIR não derruba o processo (I19)
# ---------------------------------------------------------------------------


class PreparoDoLogDirTest(SimpleTestCase):
    """
    Regressão de I19.

    O `LOG_DIR.mkdir()` estava solto no import do settings. Num filesystem
    read-only — ou assim que o container deixar de rodar como root — o
    `PermissionError` sobe antes de qualquer logger existir: gunicorn, celery e
    todo `manage.py` morrem sem dizer por quê. Quem depende do diretório é só o
    `macro_errors.log`, canal secundário do qual o console já tem cópia.
    """

    def test_sem_permissao_devolve_false_e_avisa(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("read-only fs")):
            with self.assertWarns(RuntimeWarning):
                self.assertFalse(base_settings._preparar_log_dir())

    def test_diretorio_nao_gravavel_devolve_false_e_avisa(self):
        with (
            patch.object(Path, "mkdir", return_value=None),
            patch("trader_portal.settings.base.os.access", return_value=False),
        ):
            with self.assertWarns(RuntimeWarning):
                self.assertFalse(base_settings._preparar_log_dir())

    def test_caminho_normal_devolve_true(self):
        self.assertTrue(base_settings._preparar_log_dir())
