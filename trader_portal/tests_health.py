"""Testes do endpoint de saúde."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from macro.models import MacroScore
from trader_portal.health import _checar_banco


def _ciclo(minutos_atras: int) -> MacroScore:
    return MacroScore.objects.create(
        measurement_time=timezone.now() - timedelta(minutes=minutos_atras),
        total_score=1,
        variation_sum=0.5,
    )


class HealthzTest(TestCase):
    """
    O endpoint existe porque HTTP 200 na home não prova nada: durante um deploy
    o site respondeu 200 o tempo todo com a coleta completamente parada.
    """

    def setUp(self):
        self.url = reverse("healthz")

    def test_tudo_saudavel_responde_200(self):
        _ciclo(minutos_atras=3)
        with patch("macro.services.utils.is_market_closed", return_value=False):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        corpo = response.json()
        self.assertEqual(corpo["status"], "ok")
        self.assertEqual(corpo["checks"]["banco"], "ok")
        self.assertEqual(corpo["checks"]["cache"], "ok")

    def test_coleta_atrasada_com_mercado_aberto_responde_503(self):
        _ciclo(minutos_atras=90)
        with patch("macro.services.utils.is_market_closed", return_value=False):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        corpo = response.json()
        self.assertEqual(corpo["status"], "degradado")
        self.assertIn("atrasado", corpo["checks"]["coleta"]["status"])
        self.assertEqual(corpo["checks"]["coleta"]["idade_minutos"], 90)

    def test_coleta_atrasada_com_mercado_fechado_responde_200(self):
        """Alerta que toca toda madrugada é alerta que ninguém lê."""
        _ciclo(minutos_atras=600)
        with patch("macro.services.utils.is_market_closed", return_value=True):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("mercado fechado", response.json()["checks"]["coleta"]["status"])

    def test_sem_ciclo_nenhum_responde_503(self):
        with patch("macro.services.utils.is_market_closed", return_value=True):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["coleta"]["status"], "nenhum ciclo registrado")

    def test_redis_degradado_e_detectado(self):
        """
        O `ResilientRedisCache` engole a falha de propósito e devolve None. Um
        `set` sem `get` diria "ok" com o Redis fora — que é justamente o tipo de
        200 mentiroso que este endpoint existe para evitar.
        """
        _ciclo(minutos_atras=3)
        with (
            patch("macro.services.utils.is_market_closed", return_value=False),
            patch("trader_portal.health.cache.get", return_value=None),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["cache"], "sem resposta do redis")

    def test_checagem_de_banco_reporta_falha(self):
        """
        A checagem é testada direto, e não pela view: com `ATOMIC_REQUESTS`
        ligado, o middleware abre transação na mesma conexão antes de a view
        rodar, então derrubar `connection.cursor` mataria a requisição antes de
        chegar no endpoint — testaria o Django, não o nosso código.
        """
        with patch(
            "trader_portal.health.connection.cursor", side_effect=OSError("conexao recusada")
        ):
            saudavel, detalhe = _checar_banco()

        self.assertFalse(saudavel)
        self.assertIn("erro", detalhe)

    def test_banco_fora_derruba_o_endpoint_para_503(self):
        _ciclo(minutos_atras=3)
        with (
            patch("macro.services.utils.is_market_closed", return_value=False),
            patch(
                "trader_portal.health._checar_banco",
                return_value=(False, "erro: OperationalError"),
            ),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertIn("erro", response.json()["checks"]["banco"])

    def test_resposta_nao_e_cacheada(self):
        _ciclo(minutos_atras=3)
        with patch("macro.services.utils.is_market_closed", return_value=False):
            response = self.client.get(self.url)

        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))
