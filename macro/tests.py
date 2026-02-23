"""
Testes do app macro - utils, parsers, collector e views.
"""
from datetime import datetime
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Plan
from accounts.tests import create_profile, create_user

from .models import MacroAsset, MacroScore, MacroVariation, SourceChoices
from .services.collector import _compute_score_and_adjusted_variation, execute_cycle
from .services.parsers import parse_investing_variation, parse_tradingview_variation
from .services.utils import align_measurement_time, is_market_closed, parse_variation_percent


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------


class ParseVariationPercentTest(TestCase):
    """Testes de parse_variation_percent."""

    def test_retorna_none_para_valor_nulo(self):
        self.assertIsNone(parse_variation_percent(None))

    def test_retorna_none_para_string_vazia(self):
        self.assertIsNone(parse_variation_percent(""))
        self.assertIsNone(parse_variation_percent("   "))

    def test_converte_percentual_positivo(self):
        self.assertAlmostEqual(parse_variation_percent("0,36%"), 0.0036)
        self.assertAlmostEqual(parse_variation_percent("1.5%"), 0.015)

    def test_converte_percentual_negativo(self):
        self.assertAlmostEqual(parse_variation_percent("-0,25%"), -0.0025)
        self.assertAlmostEqual(parse_variation_percent("-1%"), -0.01)

    def test_aceita_unicode_minus(self):
        self.assertAlmostEqual(parse_variation_percent("\u2212 0,5%"), -0.005)

    def test_retorna_none_sem_percentual(self):
        self.assertIsNone(parse_variation_percent("abc"))
        self.assertIsNone(parse_variation_percent("123"))


class AlignMeasurementTimeTest(TestCase):
    """Testes de align_measurement_time."""

    def test_alinha_para_intervalo_de_5_minutos(self):
        dt = timezone.make_aware(datetime(2025, 2, 22, 12, 7, 30))
        result = align_measurement_time(dt, interval_minutes=5)
        self.assertEqual(result.minute, 5)
        self.assertEqual(result.second, 0)
        self.assertEqual(result.microsecond, 0)

    def test_alinha_12_03_para_12_00(self):
        dt = timezone.make_aware(datetime(2025, 2, 22, 12, 3, 0))
        result = align_measurement_time(dt, interval_minutes=5)
        self.assertEqual(result.minute, 0)

    def test_alinha_12_09_para_12_05(self):
        dt = timezone.make_aware(datetime(2025, 2, 22, 12, 9, 0))
        result = align_measurement_time(dt, interval_minutes=5)
        self.assertEqual(result.minute, 5)


class IsMarketClosedTest(TestCase):
    """Testes de is_market_closed (sex 19h até dom 19h)."""

    def test_sexta_19h_retorna_true(self):
        dt = timezone.make_aware(datetime(2025, 2, 21, 19, 0, 0))  # sexta
        self.assertTrue(is_market_closed(dt))

    def test_sexta_18h_retorna_false(self):
        dt = timezone.make_aware(datetime(2025, 2, 21, 18, 59, 0))
        self.assertFalse(is_market_closed(dt))

    def test_sabado_retorna_true(self):
        dt = timezone.make_aware(datetime(2025, 2, 22, 12, 0, 0))  # sábado
        self.assertTrue(is_market_closed(dt))

    def test_domingo_antes_19h_retorna_true(self):
        dt = timezone.make_aware(datetime(2025, 2, 23, 18, 0, 0))  # domingo
        self.assertTrue(is_market_closed(dt))

    def test_domingo_19h_retorna_false(self):
        dt = timezone.make_aware(datetime(2025, 2, 23, 19, 0, 0))  # domingo 19h
        self.assertFalse(is_market_closed(dt))

    def test_segunda_retorna_false(self):
        dt = timezone.make_aware(datetime(2025, 2, 24, 10, 0, 0))  # segunda
        self.assertFalse(is_market_closed(dt))


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


class ParseInvestingVariationTest(TestCase):
    """Testes de parse_investing_variation."""

    def test_retorna_none_para_html_vazio(self):
        self.assertIsNone(parse_investing_variation(""))
        self.assertIsNone(parse_investing_variation(None))

    def test_extrai_de_json_com_percent(self):
        html = '{"data": {"changePercent": 0.36}}'
        result = parse_investing_variation(html)
        self.assertIsNotNone(result)
        self.assertIn("%", result)

    def test_extrai_de_html_com_data_test(self):
        html = '<span data-test="instrument-price-change-percent">+0,36%</span>'
        result = parse_investing_variation(html)
        self.assertIsNotNone(result)
        self.assertIn("%", result)


class ParseTradingviewVariationTest(TestCase):
    """Testes de parse_tradingview_variation."""

    def test_retorna_none_para_html_vazio(self):
        self.assertIsNone(parse_tradingview_variation(""))
        self.assertIsNone(parse_tradingview_variation(None))

    def test_extrai_de_json_com_change_percent(self):
        html = '{"changePercent": -0.25}'
        result = parse_tradingview_variation(html)
        self.assertIsNotNone(result)
        self.assertIn("%", result)

    def test_extrai_ext_de_span(self):
        html = '<span class="js-symbol-ext-hrs-change-pt">-0.15%</span>'
        result = parse_tradingview_variation(html)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("EXT:"))

    def test_extrai_reg_de_span(self):
        html = '<span class="js-symbol-change-pt">+0.20%</span>'
        result = parse_tradingview_variation(html)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("REG:"))


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class ComputeScoreAndAdjustedVariationTest(TestCase):
    """Testes de _compute_score_and_adjusted_variation."""

    def _create_asset(self, value_base: float):
        return MacroAsset(
            name="Test",
            url="https://example.com",
            value_base=value_base,
            source_key=SourceChoices.INVESTING,
        )

    def test_variation_none_retorna_score_zero(self):
        asset = self._create_asset(0.5)
        score, adj = _compute_score_and_adjusted_variation(asset, None)
        self.assertEqual(score, 0)
        self.assertEqual(adj, 0.0)

    def test_value_base_positivo_variation_acima_threshold_retorna_1(self):
        asset = self._create_asset(0.5)
        score, adj = _compute_score_and_adjusted_variation(asset, 0.6)
        self.assertEqual(score, 1)
        self.assertAlmostEqual(adj, 0.6)

    def test_value_base_positivo_variation_abaixo_negativo_retorna_menos_1(self):
        asset = self._create_asset(0.5)
        score, adj = _compute_score_and_adjusted_variation(asset, -0.6)
        self.assertEqual(score, -1)
        self.assertAlmostEqual(adj, -0.6)

    def test_value_base_negativo_inverte_direcao(self):
        asset = self._create_asset(-0.5)
        score, adj = _compute_score_and_adjusted_variation(asset, 0.6)
        self.assertEqual(score, -1)
        self.assertAlmostEqual(adj, -0.6)


class ExecuteCycleTest(TestCase):
    """Testes de execute_cycle com mock de fetch_html."""

    def setUp(self):
        self.asset = MacroAsset.objects.create(
            name="Test Asset",
            url="https://br.investing.com/test",
            value_base=0.5,
            source_key=SourceChoices.INVESTING,
            active=True,
        )

    @patch("macro.services.collector.fetch_html")
    def test_execute_cycle_persiste_variacao_e_score(self, mock_fetch):
        from macro.services.network import FetchOutcome

        # +50% -> variation_decimal=0.5; com value_base=0.5, score=1 (0.5 >= 0.5)
        mock_fetch.return_value = FetchOutcome(
            html='<span data-test="instrument-price-change-percent">+50%</span>',
            status="ok",
        )
        measurement_time = timezone.make_aware(datetime(2025, 2, 24, 10, 5, 0))

        execute_cycle(measurement_time)

        self.assertEqual(MacroVariation.objects.count(), 1)
        self.assertEqual(MacroScore.objects.count(), 1)
        score = MacroScore.objects.get()
        self.assertEqual(score.total_score, 1)
        self.assertAlmostEqual(score.variation_sum, 0.5)

    @patch("macro.services.collector.is_market_closed")
    def test_execute_cycle_nao_coleta_quando_mercado_fechado(self, mock_closed):
        mock_closed.return_value = True
        measurement_time = timezone.make_aware(datetime(2025, 2, 22, 20, 0, 0))

        execute_cycle(measurement_time)

        self.assertEqual(MacroVariation.objects.count(), 0)
        self.assertEqual(MacroScore.objects.count(), 0)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class LatestScoresViewTest(TestCase):
    """Testes da view latest_scores."""

    def test_retorna_200_com_results_vazio(self):
        response = self.client.get(reverse("macro:latest_scores"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertEqual(data["results"], [])

    def test_respeita_limit(self):
        for i in range(5):
            MacroScore.objects.create(
                measurement_time=timezone.now() - timezone.timedelta(hours=i),
                total_score=i,
                variation_sum=float(i),
            )
        response = self.client.get(reverse("macro:latest_scores") + "?limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 2)

    def test_limit_invalido_usa_default(self):
        response = self.client.get(reverse("macro:latest_scores") + "?limit=abc")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)

    def test_aceita_anonimo(self):
        response = self.client.get(reverse("macro:latest_scores"))
        self.assertEqual(response.status_code, 200)


class LatestVariationsViewTest(TestCase):
    """Testes da view latest_variations."""

    def setUp(self):
        self.asset = MacroAsset.objects.create(
            name="Test",
            url="https://example.com",
            value_base=0.5,
            source_key=SourceChoices.INVESTING,
        )

    def test_retorna_200_com_results_vazio(self):
        response = self.client.get(reverse("macro:latest_variations"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertEqual(data["results"], [])

    def test_retorna_variacoes_com_asset(self):
        MacroVariation.objects.create(
            asset=self.asset,
            measurement_time=timezone.now(),
            variation_text="+0.5%",
            variation_decimal=0.005,
            status="ok",
        )
        response = self.client.get(reverse("macro:latest_variations"))
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["asset"], "Test")
        self.assertEqual(results[0]["variation_text"], "+0.5%")

    def test_filtra_por_since(self):
        old_time = timezone.now() - timezone.timedelta(days=2)
        MacroVariation.objects.create(
            asset=self.asset,
            measurement_time=old_time,
            variation_text="+0.5%",
            variation_decimal=0.005,
            status="ok",
        )
        since = (timezone.now() - timezone.timedelta(days=1)).isoformat()
        response = self.client.get(
            reverse("macro:latest_variations") + "?" + urlencode({"since": since})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 0)


class SMCDashboardViewTest(TestCase):
    """Testes das views de painel (PlanRequiredMixin)."""

    def setUp(self):
        self.user_free = create_user(email="free@test.com")
        create_profile(self.user_free, plan=Plan.FREE)
        self.user_basic = create_user(email="basic@test.com")
        create_profile(self.user_basic, plan=Plan.BASIC)

    def test_usuario_free_redirecionado_ao_painel(self):
        self.client.force_login(self.user_free)
        response = self.client.get(reverse("macro:painel"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("trades:dashboard"))

    def test_usuario_basic_acessa_painel(self):
        self.client.force_login(self.user_basic)
        response = self.client.get(reverse("macro:painel"))
        self.assertEqual(response.status_code, 200)

    def test_anonimo_redirecionado_para_login(self):
        response = self.client.get(reverse("macro:painel"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
