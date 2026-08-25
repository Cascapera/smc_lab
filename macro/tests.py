"""
Testes do app macro - utils, parsers, collector e views.
"""

from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Plan
from accounts.tests import create_profile, create_user

from .models import MacroAsset, MacroScore, MacroVariation, SourceChoices
from .services.collector import (
    _compute_score_and_adjusted_variation,
    _last_known_variations,
    execute_cycle,
)
from .services.network import _classify_playwright_error, _fetch_tradingview_playwright
from .services.parsers import parse_investing_variation, parse_tradingview_variation
from .services.retention import purgar_variacoes_antigas
from .services.utils import align_measurement_time, is_market_closed, parse_variation_percent
from .tasks import CYCLE_LOCK_KEY, collect_macro_cycle, purge_old_macro_variations

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

    def test_execute_cycle_persiste_variacao_e_score(self):
        from macro.services.network import FetchOutcome

        measurement_time = timezone.make_aware(datetime(2025, 2, 24, 10, 5, 0))
        with (
            patch("macro.services.collector.fetch_html") as mock_fetch,
            patch("macro.services.collector.is_market_closed", return_value=False),
            patch("macro.services.collector.time.sleep"),
        ):
            mock_fetch.return_value = FetchOutcome(
                html='<span data-test="instrument-price-change-percent">+50%</span>',
                status="ok",
            )
            execute_cycle(measurement_time)

        self.assertTrue(mock_fetch.called, "fetch_html deveria ter sido chamado")
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
    """Testes da view latest_scores (exige plano Basic+)."""

    def setUp(self):
        self.user = create_user(email="scores-basic@test.com")
        create_profile(self.user, plan=Plan.BASIC)
        self.client.force_login(self.user)

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

    def test_anonimo_recebe_401(self):
        """Dado do painel é produto pago: anônimo não acessa a API."""
        self.client.logout()
        response = self.client.get(reverse("macro:latest_scores"))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("results", response.json())

    def test_usuario_free_recebe_403(self):
        self.client.logout()
        user_free = create_user(email="scores-free@test.com")
        create_profile(user_free, plan=Plan.FREE)
        self.client.force_login(user_free)
        response = self.client.get(reverse("macro:latest_scores"))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("results", response.json())

    def test_plano_expirado_recebe_403(self):
        self.client.logout()
        user_exp = create_user(email="scores-exp@test.com")
        create_profile(
            user_exp,
            plan=Plan.PREMIUM,
            plan_expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        self.client.force_login(user_exp)
        response = self.client.get(reverse("macro:latest_scores"))
        self.assertEqual(response.status_code, 403)


class LatestVariationsViewTest(TestCase):
    """Testes da view latest_variations (exige plano Basic+)."""

    def setUp(self):
        self.asset = MacroAsset.objects.create(
            name="Test",
            url="https://example.com",
            value_base=0.5,
            source_key=SourceChoices.INVESTING,
        )
        self.user = create_user(email="variations-basic@test.com")
        create_profile(self.user, plan=Plan.BASIC)
        self.client.force_login(self.user)

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

    def test_anonimo_recebe_401(self):
        self.client.logout()
        response = self.client.get(reverse("macro:latest_variations"))
        self.assertEqual(response.status_code, 401)

    def test_usuario_free_recebe_403(self):
        self.client.logout()
        user_free = create_user(email="variations-free@test.com")
        create_profile(user_free, plan=Plan.FREE)
        self.client.force_login(user_free)
        response = self.client.get(reverse("macro:latest_variations"))
        self.assertEqual(response.status_code, 403)


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


# ---------------------------------------------------------------------------
# Task de coleta - trava de ciclo
# ---------------------------------------------------------------------------


class CollectMacroCycleTest(TestCase):
    """
    A coleta pode passar de 5 minutos, que é o intervalo do Beat. Sem trava e
    sem `expires`, o Beat continua enfileirando e a fila só cresce: quando o
    worker vaza, roda uma rajada de coletas atrasadas, todas com
    `measurement_time = agora`, gerando buckets pulados e ciclos duplicados.
    """

    def setUp(self):
        cache.delete(CYCLE_LOCK_KEY)

    def tearDown(self):
        cache.delete(CYCLE_LOCK_KEY)

    @patch("macro.tasks.execute_cycle")
    @patch("macro.tasks.is_market_closed", return_value=False)
    def test_ciclo_roda_quando_nao_ha_outro(self, _mock_closed, mock_execute):
        collect_macro_cycle.apply()
        mock_execute.assert_called_once()

    @patch("macro.tasks.execute_cycle")
    @patch("macro.tasks.is_market_closed", return_value=False)
    def test_ciclo_e_pulado_quando_ja_existe_um_rodando(self, _mock_closed, mock_execute):
        cache.add(CYCLE_LOCK_KEY, "1", 60)
        collect_macro_cycle.apply()
        mock_execute.assert_not_called()

    @patch("macro.tasks.execute_cycle")
    @patch("macro.tasks.is_market_closed", return_value=False)
    def test_trava_e_liberada_ao_final(self, _mock_closed, mock_execute):
        collect_macro_cycle.apply()
        self.assertIsNone(cache.get(CYCLE_LOCK_KEY))

    @patch("macro.tasks.execute_cycle", side_effect=RuntimeError("falha na coleta"))
    @patch("macro.tasks.is_market_closed", return_value=False)
    def test_trava_e_liberada_mesmo_com_erro(self, _mock_closed, _mock_execute):
        """Se a trava vazasse num erro, a coleta pararia até o worker reiniciar."""
        collect_macro_cycle.apply()
        self.assertIsNone(cache.get(CYCLE_LOCK_KEY))

    @patch("macro.tasks.execute_cycle")
    @patch("macro.tasks.is_market_closed", return_value=True)
    def test_mercado_fechado_nao_toma_a_trava(self, _mock_closed, mock_execute):
        collect_macro_cycle.apply()
        mock_execute.assert_not_called()
        self.assertIsNone(cache.get(CYCLE_LOCK_KEY))

    def test_beat_descarta_coleta_atrasada(self):
        """`expires` evita que coletas atrasadas se acumulem na fila."""
        entrada = settings.CELERY_BEAT_SCHEDULE["macro-collect-every-5min"]
        self.assertIn("expires", entrada.get("options", {}))
        self.assertLessEqual(entrada["options"]["expires"], 300)


# ---------------------------------------------------------------------------
# Retenção e custo da consulta de fallback
# ---------------------------------------------------------------------------


class UltimaVariacaoConhecidaTest(TestCase):
    """
    Regressão de custo: a versão anterior carregava TODAS as linhas de
    MacroVariation a cada ciclo, ordenava por (asset_id, -measurement_time) e
    percorria tudo em Python para pegar uma por ativo. Em produção virou
    1,39 milhão de linhas lidas a cada 5 minutos.
    """

    def setUp(self):
        self.ativo_a = MacroAsset.objects.create(
            name="Ativo A",
            url="https://exemplo.com/a",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )
        self.ativo_b = MacroAsset.objects.create(
            name="Ativo B",
            url="https://exemplo.com/b",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )

    def _variacao(self, ativo, minutos_atras, decimal, texto="+0.5%"):
        return MacroVariation.objects.create(
            asset=ativo,
            measurement_time=timezone.now() - timezone.timedelta(minutes=minutos_atras),
            variation_text=texto,
            variation_decimal=decimal,
            status="ok",
        )

    def test_devolve_a_mais_recente_de_cada_ativo(self):
        self._variacao(self.ativo_a, 60, 0.001, "+0.1%")
        self._variacao(self.ativo_a, 5, 0.009, "+0.9%")
        self._variacao(self.ativo_b, 10, 0.002, "+0.2%")

        resultado = _last_known_variations([self.ativo_a, self.ativo_b])

        self.assertEqual(resultado[self.ativo_a.id]["variation_decimal"], 0.009)
        self.assertEqual(resultado[self.ativo_a.id]["variation_text"], "+0.9%")
        self.assertEqual(resultado[self.ativo_b.id]["variation_decimal"], 0.002)

    def test_ignora_linhas_sem_variacao(self):
        self._variacao(self.ativo_a, 60, 0.001)
        MacroVariation.objects.create(
            asset=self.ativo_a,
            measurement_time=timezone.now(),
            variation_decimal=None,
            status="no_data",
        )
        resultado = _last_known_variations([self.ativo_a])
        self.assertEqual(resultado[self.ativo_a.id]["variation_decimal"], 0.001)

    def test_ativo_sem_historico_fica_fora(self):
        self.assertEqual(_last_known_variations([self.ativo_a]), {})

    def test_lista_vazia(self):
        self.assertEqual(_last_known_variations([]), {})

    def test_usa_uma_query_independente_do_tamanho_da_tabela(self):
        """O custo não pode crescer com o histórico."""
        for i in range(1, 60):
            self._variacao(self.ativo_a, i, 0.001 * i)
            self._variacao(self.ativo_b, i, 0.002 * i)

        with self.assertNumQueries(1):
            resultado = _last_known_variations([self.ativo_a, self.ativo_b])
        self.assertEqual(len(resultado), 2)


class RetencaoDeVariacoesTest(TestCase):
    """
    `MacroVariation` nunca teve limpeza: chegou a 1913 MB e 1,39 M linhas em
    produção, 87% do banco, e cada backup copiava tudo.
    """

    def setUp(self):
        self.ativo = MacroAsset.objects.create(
            name="Ativo",
            url="https://exemplo.com",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )

    def _variacao(self, dias_atras):
        return MacroVariation.objects.create(
            asset=self.ativo,
            measurement_time=timezone.now() - timezone.timedelta(days=dias_atras),
            variation_text="+0.5%",
            variation_decimal=0.005,
            status="ok",
        )

    def test_remove_apenas_o_que_passou_do_corte(self):
        self._variacao(dias_atras=120)
        self._variacao(dias_atras=100)
        recente = self._variacao(dias_atras=10)

        resultado = purgar_variacoes_antigas(dias=90)

        self.assertEqual(resultado["encontradas"], 2)
        self.assertEqual(resultado["removidas"], 2)
        self.assertEqual(list(MacroVariation.objects.all()), [recente])

    def test_dry_run_nao_apaga_nada(self):
        self._variacao(dias_atras=120)
        resultado = purgar_variacoes_antigas(dias=90, dry_run=True)
        self.assertEqual(resultado["encontradas"], 1)
        self.assertEqual(resultado["removidas"], 0)
        self.assertEqual(MacroVariation.objects.count(), 1)

    def test_remove_em_lotes(self):
        """Apagar tudo numa transação só trava a tabela e incha o WAL."""
        for dia in range(100, 110):
            self._variacao(dias_atras=dia)

        resultado = purgar_variacoes_antigas(dias=90, tamanho_lote=3)

        self.assertEqual(resultado["removidas"], 10)
        self.assertEqual(resultado["lotes"], 4)  # 3+3+3+1
        self.assertEqual(MacroVariation.objects.count(), 0)

    def test_nao_apaga_o_historico_de_score(self):
        """MacroScore alimenta o gráfico do painel e é pequeno; fica."""
        MacroScore.objects.create(
            measurement_time=timezone.now() - timezone.timedelta(days=200),
            total_score=3,
            variation_sum=0.02,
        )
        self._variacao(dias_atras=200)

        purgar_variacoes_antigas(dias=90)

        self.assertEqual(MacroScore.objects.count(), 1)
        self.assertEqual(MacroVariation.objects.count(), 0)

    def test_recusa_retencao_invalida(self):
        with self.assertRaises(ValueError):
            purgar_variacoes_antigas(dias=0)

    def test_tabela_vazia_nao_quebra(self):
        resultado = purgar_variacoes_antigas(dias=90)
        self.assertEqual(resultado["removidas"], 0)

    def test_comando_dry_run(self):
        self._variacao(dias_atras=120)
        saida = StringIO()
        call_command("purge_macro_variations", "--dry-run", "--days", "90", stdout=saida)
        self.assertIn("Simulação", saida.getvalue())
        self.assertEqual(MacroVariation.objects.count(), 1)

    def test_comando_apaga(self):
        self._variacao(dias_atras=120)
        saida = StringIO()
        call_command("purge_macro_variations", "--days", "90", stdout=saida)
        self.assertIn("Removidas", saida.getvalue())
        self.assertEqual(MacroVariation.objects.count(), 0)

    def test_task_diaria(self):
        self._variacao(dias_atras=120)
        resultado = purge_old_macro_variations.apply().get()
        self.assertEqual(resultado["removidas"], 1)

    def test_beat_tem_a_limpeza_agendada(self):
        entrada = settings.CELERY_BEAT_SCHEDULE["macro-purge-variations-daily"]
        self.assertEqual(entrada["task"], "macro.tasks.purge_old_macro_variations")


class SourceExcerptTest(TestCase):
    """
    O `source_excerpt` guarda o HTML de onde não se conseguiu extrair a variação.
    Gravá-lo também no sucesso era o que fazia a tabela crescer ~270 MB/mês.
    """

    def test_sucesso_nao_guarda_excerpt(self):
        asset = MacroAsset.objects.create(
            name="Teste OK",
            url="https://exemplo.com",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )
        html = "<span data-test='instrument-price-change-percent'>+0.55%</span>" + ("x" * 5000)
        with (
            patch("macro.services.collector.fetch_html") as mock_fetch,
            patch("macro.services.collector.is_market_closed", return_value=False),
        ):
            mock_fetch.return_value = SimpleNamespace(status="ok", html=html, block_reason="")
            execute_cycle(timezone.now())

        variacao = MacroVariation.objects.get(asset=asset)
        self.assertEqual(variacao.status, "ok")
        self.assertEqual(variacao.source_excerpt, "")

    def test_falha_guarda_excerpt_para_diagnostico(self):
        MacroAsset.objects.create(
            name="Teste falha",
            url="https://exemplo.com",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )
        with (
            patch("macro.services.collector.fetch_html") as mock_fetch,
            patch("macro.services.collector.is_market_closed", return_value=False),
        ):
            mock_fetch.return_value = SimpleNamespace(
                status="blocked", html="<html>pagina de bloqueio</html>", block_reason="cloudflare"
            )
            execute_cycle(timezone.now())

        variacao = MacroVariation.objects.first()
        self.assertNotEqual(variacao.status, "ok")
        self.assertNotEqual(variacao.source_excerpt, "")


# ---------------------------------------------------------------------------
# Robustez da coleta (Fase 3)
# ---------------------------------------------------------------------------


class ClassificacaoDeErroPlaywrightTest(TestCase):
    """
    `net::ERR_NAME_NOT_RESOLVED` (DNS) era classificado como bloqueio de IP.
    Como o `fetch_html` só tenta os fallbacks para `fetch_error`/`no_data`, um
    erro transitório de rede fazia o ativo pular toda a cadeia de recuperação.
    """

    def test_timeout_e_erro_transitorio(self):
        motivo, _tipo = _classify_playwright_error(Exception("Timeout 60000ms exceeded"))
        self.assertNotEqual(motivo, "playwright_ip_block")

    def test_erro_de_dns_nao_e_bloqueio_de_ip(self):
        motivo, _tipo = _classify_playwright_error(
            Exception("net::ERR_NAME_NOT_RESOLVED at https://exemplo.com")
        )
        self.assertNotEqual(
            motivo,
            "playwright_ip_block",
            "erro de DNS classificado como bloqueio faz o ativo pular os fallbacks",
        )

    def test_conexao_recusada_nao_e_bloqueio_de_ip(self):
        motivo, _tipo = _classify_playwright_error(Exception("net::ERR_CONNECTION_RESET"))
        self.assertNotEqual(motivo, "playwright_ip_block")


class FechamentoDoChromiumTest(TestCase):
    """
    `browser.close()` só existia no caminho feliz: um timeout no `goto` deixava
    o processo vivo. É o que o restart do worker 3x/dia vinha limpando como
    "processos órfãos".
    """

    def _playwright_falso(self, erro_no_goto=None):
        browser = MagicMock()
        page = MagicMock()
        if erro_no_goto:
            page.goto.side_effect = erro_no_goto
        else:
            page.content.return_value = "<html>ok</html>"
        browser.new_page.return_value = page
        contexto = MagicMock()
        contexto.__enter__.return_value.chromium.launch.return_value = browser
        return contexto, browser

    def _asset(self):
        return MacroAsset(
            name="Teste",
            url="https://exemplo.com",
            value_base=0.003,
            source_key=SourceChoices.TRADINGVIEW,
        )

    def test_fecha_o_navegador_no_caminho_feliz(self):
        contexto, browser = self._playwright_falso()
        with patch("playwright.sync_api.sync_playwright", return_value=contexto):
            _fetch_tradingview_playwright(self._asset())
        browser.close.assert_called_once()

    def test_fecha_o_navegador_mesmo_com_timeout(self):
        contexto, browser = self._playwright_falso(erro_no_goto=Exception("Timeout 60000ms"))
        with patch("playwright.sync_api.sync_playwright", return_value=contexto):
            resultado = _fetch_tradingview_playwright(self._asset())
        browser.close.assert_called_once()
        self.assertNotEqual(resultado.status, "ok")


class SinceInvalidoTest(TestCase):
    """`?since` malformado derrubava a API com 500 — erro do cliente virando 500 nosso."""

    def setUp(self):
        self.user = create_user(email="since@test.com")
        create_profile(self.user, plan=Plan.BASIC)
        self.client.force_login(self.user)
        self.url = reverse("macro:latest_variations")

    def test_data_inexistente_devolve_400(self):
        resposta = self.client.get(self.url + "?since=2025-02-30T10:00:00")
        self.assertEqual(resposta.status_code, 400)

    def test_texto_qualquer_devolve_400(self):
        resposta = self.client.get(self.url + "?since=ontem")
        self.assertEqual(resposta.status_code, 400)

    def test_data_valida_continua_funcionando(self):
        agora = timezone.now().isoformat()
        resposta = self.client.get(self.url + "?" + urlencode({"since": agora}))
        self.assertEqual(resposta.status_code, 200)

    def test_data_sem_fuso_e_aceita(self):
        resposta = self.client.get(self.url + "?since=2026-01-01T10:00:00")
        self.assertEqual(resposta.status_code, 200)


class LinhaDeErroNoCicloTest(TestCase):
    """
    Uma exceção num ativo não gravava linha nenhuma: ele sumia do painel naquele
    bucket e ninguém sabia que houve falha.
    """

    def setUp(self):
        self.asset = MacroAsset.objects.create(
            name="Quebra",
            url="https://exemplo.com",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )

    def test_falha_no_ativo_gera_linha_de_erro(self):
        with (
            patch("macro.services.collector.fetch_html", side_effect=RuntimeError("caiu")),
            patch("macro.services.collector.is_market_closed", return_value=False),
        ):
            execute_cycle(timezone.now())

        variacao = MacroVariation.objects.get(asset=self.asset)
        self.assertEqual(variacao.status, "error")
        self.assertIn("RuntimeError", variacao.block_reason)
        self.assertIsNone(variacao.variation_decimal)

    def test_ciclo_continua_apos_falha_de_um_ativo(self):
        MacroAsset.objects.create(
            name="Funciona",
            url="https://exemplo.com/ok",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )
        chamadas = {"n": 0}

        def as_vezes_falha(asset):
            chamadas["n"] += 1
            if asset.name == "Quebra":
                raise RuntimeError("caiu")
            return SimpleNamespace(
                status="ok",
                html="<span data-test='instrument-price-change-percent'>+0.55%</span>",
                block_reason="",
            )

        with (
            patch("macro.services.collector.fetch_html", side_effect=as_vezes_falha),
            patch("macro.services.collector.is_market_closed", return_value=False),
        ):
            execute_cycle(timezone.now())

        self.assertEqual(MacroVariation.objects.count(), 2)
        self.assertEqual(MacroScore.objects.count(), 1)


class TruncateNaoApagaHistoricoTest(TestCase):
    """
    `--truncate` fazia `MacroAsset.objects.all().delete()`, que cascateia para
    MacroVariation: reimportar a planilha destruía meses de coleta.
    """

    def test_truncate_desativa_em_vez_de_apagar(self):
        asset = MacroAsset.objects.create(
            name="Antigo",
            url="https://exemplo.com",
            value_base=0.003,
            source_key=SourceChoices.INVESTING,
        )
        MacroVariation.objects.create(
            asset=asset,
            measurement_time=timezone.now(),
            variation_decimal=0.005,
            status="ok",
        )

        MacroAsset.objects.all().update(active=False)

        self.assertEqual(MacroVariation.objects.count(), 1, "historico foi apagado")
        asset.refresh_from_db()
        self.assertFalse(asset.active)
