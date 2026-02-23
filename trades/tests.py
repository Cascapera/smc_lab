"""
Testes do app trades - CRUD, analytics, forms, views e llm_service.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Plan
from accounts.tests import create_profile, create_user

from .analytics import (
    compute_advanced_metrics,
    compute_drawdown_series,
    compute_global_dashboard,
    compute_profit_factor_payoff,
    compute_streaks,
    compute_user_dashboard,
)
from .forms import TradeForm
from .llm_service import AnalyticsLLMError, run_analytics_llm, run_global_analytics_llm
from .models import (
    AIAnalyticsRun,
    Direction,
    EntryType,
    GlobalAIAnalyticsRun,
    HighTimeFrame,
    Market,
    PartialTrade,
    PremiumDiscount,
    RegionHTF,
    ResultType,
    Setup,
    SMCPanel,
    Trade,
    Trend,
    Trigger,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Factories / Fixtures
# ---------------------------------------------------------------------------

# PNG mínimo válido (1x1 pixel)
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def valid_trade_data(**overrides):
    """Retorna dicionário com dados válidos para TradeForm."""
    now = timezone.localtime().replace(microsecond=0)
    data = {
        "executed_at": now.strftime("%Y-%m-%dT%H:%M"),
        "symbol": "petr4",
        "market": Market.STOCKS,
        "direction": Direction.BUY,
        "quantity": "100",
        "high_time_frame": HighTimeFrame.M15,
        "trend": Trend.BULLISH,
        "smc_panel": SMCPanel.OPTIMISTIC,
        "premium_discount": PremiumDiscount.BUY_DISCOUNT,
        "region_htf": RegionHTF.PRIMARY,
        "entry_type": EntryType.CONFIRMED,
        "setup": Setup.FLIP,
        "trigger": Trigger.REGION,
        "target_price": "25.50",
        "stop_price": "24.00",
        "partial_trade": PartialTrade.NO_DONE,
        "result_type": ResultType.GAIN,
        "currency": "BRL",
        "profit_amount": "150.00",
        "technical_gain": "140.00",
        "is_public": False,
        "display_as_anonymous": True,
        "notes": "",
    }
    data.update(overrides)
    return data


def create_trade(
    user,
    symbol: str = "PETR4",
    profit_amount: Decimal = Decimal("100.00"),
    result_type: str = ResultType.GAIN,
    is_public: bool = False,
    executed_at=None,
    **kwargs,
) -> Trade:
    """Cria um trade para testes."""
    if executed_at is None:
        executed_at = timezone.now()
    defaults = {
        "executed_at": executed_at,
        "symbol": symbol,
        "market": Market.STOCKS,
        "direction": Direction.BUY,
        "quantity": Decimal("100"),
        "high_time_frame": HighTimeFrame.M15,
        "trend": Trend.BULLISH,
        "smc_panel": SMCPanel.NEUTRAL,
        "premium_discount": PremiumDiscount.BUY_DISCOUNT,
        "region_htf": RegionHTF.PRIMARY,
        "entry_type": EntryType.CONFIRMED,
        "setup": Setup.FLIP,
        "trigger": Trigger.REGION,
        "target_price": Decimal("25.50"),
        "stop_price": Decimal("24.00"),
        "partial_trade": PartialTrade.NO_DONE,
        "result_type": result_type,
        "profit_amount": profit_amount,
        "technical_gain": profit_amount,
        "is_public": is_public,
        "display_as_anonymous": True,
    }
    defaults.update(kwargs)
    return Trade.objects.create(user=user, **defaults)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TradeModelTest(TestCase):
    """Testes do modelo Trade."""

    def setUp(self):
        self.user = create_user()

    def test_str_retorna_symbol_direcao_e_data(self):
        trade = create_trade(self.user, symbol="VALE3")
        self.assertIn("VALE3", str(trade))
        self.assertIn("Compra", str(trade))


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


class TradeFormTest(TestCase):
    """Testes do TradeForm."""

    def test_clean_symbol_converte_para_uppercase(self):
        form = TradeForm(data=valid_trade_data(symbol="petr4"))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["symbol"], "PETR4")

    def test_clean_symbol_aceita_minusculas_e_retorna_maiusculas(self):
        form = TradeForm(data=valid_trade_data(symbol="winj11"))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["symbol"], "WINJ11")

    def test_clean_symbol_remove_espacos(self):
        form = TradeForm(data=valid_trade_data(symbol="  petr4  "))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["symbol"], "PETR4")

    def test_clean_forca_display_as_anonymous_quando_is_public_false(self):
        form = TradeForm(data=valid_trade_data(is_public=False, display_as_anonymous=False))
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["display_as_anonymous"])

    def test_clean_mantem_display_as_anonymous_quando_is_public_true(self):
        form = TradeForm(data=valid_trade_data(is_public=True, display_as_anonymous=True))
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["display_as_anonymous"])


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class ComputeStreaksTest(TestCase):
    """Testes de compute_streaks."""

    def test_retorna_zeros_para_lista_vazia(self):
        self.assertEqual(compute_streaks([]), (0, 0))

    def test_longest_win_streak(self):
        amounts = [100, 50, -20, 30, 40, 50]
        win, loss = compute_streaks(amounts)
        self.assertEqual(win, 3)  # 30, 40, 50
        self.assertEqual(loss, 1)

    def test_longest_loss_streak(self):
        amounts = [-10, -20, -5, 100, -1, -2, -3]
        win, loss = compute_streaks(amounts)
        self.assertEqual(win, 1)
        self.assertEqual(loss, 3)

    def test_break_even_reseta_streak(self):
        amounts = [100, 100, 0, 50, 50]
        win, loss = compute_streaks(amounts)
        self.assertEqual(win, 2)  # 50, 50 após o 0


class ComputeProfitFactorPayoffTest(TestCase):
    """Testes de compute_profit_factor_payoff."""

    def test_retorna_none_quando_gross_loss_zero(self):
        pf, payoff = compute_profit_factor_payoff(
            Decimal("100"), Decimal("0"), Decimal("50"), Decimal("-10")
        )
        self.assertIsNone(pf)
        self.assertIsNotNone(payoff)

    def test_retorna_none_quando_avg_loss_zero(self):
        pf, payoff = compute_profit_factor_payoff(
            Decimal("100"), Decimal("-50"), Decimal("50"), Decimal("0")
        )
        self.assertIsNotNone(pf)
        self.assertIsNone(payoff)

    def test_calcula_profit_factor_corretamente(self):
        pf, payoff = compute_profit_factor_payoff(
            Decimal("200"), Decimal("-100"), Decimal("50"), Decimal("-25")
        )
        self.assertAlmostEqual(pf, 2.0)
        self.assertAlmostEqual(payoff, 2.0)


class ComputeDrawdownSeriesTest(TestCase):
    """Testes de compute_drawdown_series."""

    def test_retorna_zeros_para_balance_series_vazia(self):
        dd_series, max_dd, max_dd_pct = compute_drawdown_series([], Decimal("1000"))
        self.assertEqual(dd_series, [])
        self.assertEqual(max_dd, Decimal("0"))
        self.assertEqual(max_dd_pct, Decimal("0"))

    def test_calcula_drawdown_quando_balance_cai(self):
        balance_series = [
            {"balance": 1100},
            {"balance": 1050},
            {"balance": 900},
            {"balance": 950},
        ]
        dd_series, max_dd, max_dd_pct = compute_drawdown_series(balance_series, Decimal("1000"))
        self.assertEqual(len(dd_series), 4)
        # dd = balance - peak: 0 no pico, negativo quando abaixo
        self.assertEqual(dd_series[0], 0.0)  # 1100 = novo pico
        self.assertEqual(dd_series[1], -50.0)  # 1050 - 1100
        self.assertLess(dd_series[2], 0)  # 900 - 1100 = -200
        self.assertLess(max_dd, 0)


class ComputeAdvancedMetricsTest(TestCase):
    """Testes de compute_advanced_metrics."""

    def setUp(self):
        self.user = create_user()

    def test_retorna_nd_para_profit_factor_quando_sem_perdas(self):
        create_trade(self.user, profit_amount=Decimal("100"), result_type=ResultType.GAIN)
        trades = Trade.objects.filter(user=self.user).order_by("executed_at")
        balance_series = [{"balance": 1100, "date": "2025-01-01", "daily_profit": 100}]
        base_summary = {
            "total_trades": 1,
            "win_rate": 100,
            "total_profit": 100,
            "best_trade": 100,
            "worst_trade": 0,
        }
        result = compute_advanced_metrics(trades, balance_series, Decimal("1000"), base_summary)
        self.assertEqual(result["profit_factor"], "N/D")
        self.assertEqual(result["longest_win_streak"], 1)
        self.assertEqual(result["longest_loss_streak"], 0)


class ComputeUserDashboardTest(TestCase):
    """Testes de compute_user_dashboard."""

    def setUp(self):
        self.user = create_user()
        create_profile(self.user)

    def test_retorna_summary_vazio_quando_sem_trades(self):
        result = compute_user_dashboard(self.user)
        self.assertEqual(result["summary"]["total_trades"], 0)
        self.assertEqual(result["summary"]["win_rate"], 0.0)
        self.assertEqual(result["balance_series"], [])

    def test_calcula_metricas_com_trades(self):
        create_trade(self.user, profit_amount=Decimal("100"), result_type=ResultType.GAIN)
        create_trade(self.user, profit_amount=Decimal("-50"), result_type=ResultType.LOSS)
        result = compute_user_dashboard(self.user)
        self.assertEqual(result["summary"]["total_trades"], 2)
        self.assertEqual(result["summary"]["wins"], 1)
        self.assertEqual(result["summary"]["losses"], 1)
        self.assertEqual(result["summary"]["win_rate"], 50.0)
        self.assertEqual(result["summary"]["total_profit"], 50.0)


class ComputeGlobalDashboardTest(TestCase):
    """Testes de compute_global_dashboard."""

    def test_retorna_summary_vazio_quando_sem_trades(self):
        result = compute_global_dashboard(Trade.objects.none())
        self.assertEqual(result["summary"]["total_trades"], 0)
        self.assertEqual(result["balance_series"], [])


# ---------------------------------------------------------------------------
# Views - CRUD
# ---------------------------------------------------------------------------


class TradeCreateViewTest(TestCase):
    """Testes da TradeCreateView."""

    def setUp(self):
        self.user = create_user()

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("trades:trade_add"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_autenticado_retorna_200_com_formulario(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("trades:trade_add"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_post_valido_cria_trade_e_redireciona(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("trades:trade_add"),
            data=valid_trade_data(),
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Trade.objects.filter(user=self.user).count(), 1)
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.symbol, "PETR4")

    def test_post_valido_salva_symbol_em_uppercase(self):
        self.client.force_login(self.user)
        self.client.post(reverse("trades:trade_add"), data=valid_trade_data(symbol="winj11"))
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.symbol, "WINJ11")


class TradeUpdateViewTest(TestCase):
    """Testes da TradeUpdateView."""

    def setUp(self):
        self.user = create_user()
        self.other_user = create_user(email="outro@test.com")
        self.trade = create_trade(self.user, symbol="PETR4")

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("trades:trade_edit", kwargs={"pk": self.trade.pk}))
        self.assertEqual(response.status_code, 302)

    def test_owner_acessa_formulario_de_edicao(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("trades:trade_edit", kwargs={"pk": self.trade.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], self.trade)

    def test_outro_usuario_recebe_404(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("trades:trade_edit", kwargs={"pk": self.trade.pk}))
        self.assertEqual(response.status_code, 404)

    def test_post_valido_atualiza_trade(self):
        self.client.force_login(self.user)
        data = valid_trade_data(symbol="VALE3", notes="Atualizado")
        data["executed_at"] = self.trade.executed_at.strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("trades:trade_edit", kwargs={"pk": self.trade.pk}),
            data=data,
        )
        self.assertEqual(response.status_code, 302)
        self.trade.refresh_from_db()
        self.assertEqual(self.trade.symbol, "VALE3")
        self.assertEqual(self.trade.notes, "Atualizado")


class TradeDeleteViewTest(TestCase):
    """Testes da TradeDeleteView."""

    def setUp(self):
        self.user = create_user()
        self.other_user = create_user(email="outro@test.com")
        self.trade = create_trade(self.user)

    def test_anonimo_redireciona_para_login(self):
        response = self.client.post(
            reverse("trades:trade_delete", kwargs={"pk": self.trade.pk}),
            data={"next": reverse("trades:dashboard")},
        )
        self.assertEqual(response.status_code, 302)

    def test_owner_deleta_trade(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("trades:trade_delete", kwargs={"pk": self.trade.pk}),
            data={"next": reverse("trades:dashboard")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Trade.objects.filter(pk=self.trade.pk).exists())

    def test_outro_usuario_recebe_404(self):
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse("trades:trade_delete", kwargs={"pk": self.trade.pk}),
            data={"next": reverse("trades:dashboard")},
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Trade.objects.filter(pk=self.trade.pk).exists())


# ---------------------------------------------------------------------------
# Views - Screenshot
# ---------------------------------------------------------------------------


class TradeScreenshotViewTest(TestCase):
    """Testes da TradeScreenshotView."""

    def setUp(self):
        self.user = create_user()
        self.other_user = create_user(email="outro@test.com")
        self.staff_user = create_user(email="staff@test.com", is_staff=True)

    def test_404_quando_trade_sem_screenshot(self):
        trade = create_trade(self.user)
        response = self.client.get(reverse("trades:trade_screenshot", kwargs={"pk": trade.pk}))
        self.assertEqual(response.status_code, 404)

    def test_404_quando_trade_privado_e_usuario_nao_owner(self):
        trade = create_trade(self.user, is_public=False)
        trade.screenshot = SimpleUploadedFile("test.png", MINIMAL_PNG, content_type="image/png")
        trade.save()
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("trades:trade_screenshot", kwargs={"pk": trade.pk}))
        self.assertEqual(response.status_code, 404)

    def test_200_quando_trade_publico_e_usuario_anonimo(self):
        trade = create_trade(self.user, is_public=True)
        trade.screenshot = SimpleUploadedFile("test.png", MINIMAL_PNG, content_type="image/png")
        trade.save()
        response = self.client.get(reverse("trades:trade_screenshot", kwargs={"pk": trade.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.get("Content-Type", ""))

    def test_200_quando_owner_acessa_screenshot(self):
        trade = create_trade(self.user, is_public=False)
        trade.screenshot = SimpleUploadedFile("test.png", MINIMAL_PNG, content_type="image/png")
        trade.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("trades:trade_screenshot", kwargs={"pk": trade.pk}))
        self.assertEqual(response.status_code, 200)

    def test_200_quando_staff_acessa_trade_privado(self):
        trade = create_trade(self.user, is_public=False)
        trade.screenshot = SimpleUploadedFile("test.png", MINIMAL_PNG, content_type="image/png")
        trade.save()
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("trades:trade_screenshot", kwargs={"pk": trade.pk}))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Views - Mural
# ---------------------------------------------------------------------------


class MuralViewTest(TestCase):
    """Testes da MuralView."""

    def test_retorna_200_com_mural_trades(self):
        response = self.client.get(reverse("mural"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("mural_trades", response.context)

    def test_exibe_apenas_trades_publicos_com_screenshot(self):
        user = create_user()
        create_profile(user, plan=Plan.BASIC)
        trade_public = create_trade(user, is_public=True)
        trade_public.screenshot = SimpleUploadedFile(
            "test.png", MINIMAL_PNG, content_type="image/png"
        )
        trade_public.save()
        create_trade(user, is_public=False, symbol="VALE3")
        response = self.client.get(reverse("mural"))
        self.assertEqual(response.status_code, 200)
        mural_trades = response.context["mural_trades"]
        symbols = [mt["trade"].symbol for mt in mural_trades]
        self.assertIn("PETR4", symbols)
        self.assertNotIn("VALE3", symbols)


# ---------------------------------------------------------------------------
# Views - Dashboard
# ---------------------------------------------------------------------------


class DashboardViewTest(TestCase):
    """Testes da DashboardView."""

    def setUp(self):
        self.user = create_user()

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("trades:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_autenticado_retorna_200_com_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("trades:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard", response.context)
        self.assertIn("summary", response.context["dashboard"])


# ---------------------------------------------------------------------------
# LLM Service
# ---------------------------------------------------------------------------


class AnalyticsLLMErrorTest(TestCase):
    """Testes da exceção AnalyticsLLMError."""

    def test_herda_de_exception(self):
        self.assertTrue(issubclass(AnalyticsLLMError, Exception))


class RunAnalyticsLLMTest(TestCase):
    """Testes de run_analytics_llm."""

    def test_retorna_vazio_quando_api_key_nao_configurada(self):
        with patch("trades.llm_service.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = run_analytics_llm({})
        self.assertEqual(result, "")

    @patch("trades.llm_service.settings")
    def test_levanta_analytics_llm_error_apos_retries(self, mock_settings):
        mock_settings.OPENAI_API_KEY = "sk-test"
        mock_settings.OPENAI_ANALYTICS_MODEL = "gpt-4o-mini"
        with patch("openai.OpenAI") as mock_openai:
            mock_client = mock_openai.return_value
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            with self.assertRaises(AnalyticsLLMError):
                run_analytics_llm({"top3_best_combos": [], "top3_worst_combos": []})


class RunGlobalAnalyticsLLMTest(TestCase):
    """Testes de run_global_analytics_llm."""

    def test_retorna_vazio_quando_api_key_nao_configurada(self):
        with patch("trades.llm_service.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = run_global_analytics_llm({})
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Views - Analytics IA (tratamento de erro)
# ---------------------------------------------------------------------------


class AnalyticsIAViewErrorHandlingTest(TestCase):
    """Testes do tratamento de AnalyticsLLMError na AnalyticsIAView."""

    def setUp(self):
        self.user = create_user()
        create_profile(self.user, plan=Plan.PREMIUM)
        create_trade(self.user)

    @patch("trades.llm_service.run_analytics_llm")
    def test_exibe_mensagem_amigavel_quando_llm_falha(self, mock_run):
        mock_run.side_effect = AnalyticsLLMError("Erro na API")
        self.client.force_login(self.user)
        response = self.client.post(reverse("trades:analytics_ia"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("requested=1", response.url)
        run = AIAnalyticsRun.objects.filter(user=self.user).order_by("-requested_at").first()
        self.assertIsNotNone(run)
        self.assertIn("Erro na geração do relatório", run.result)


class GlobalAnalyticsIAViewErrorHandlingTest(TestCase):
    """Testes do tratamento de AnalyticsLLMError na GlobalAnalyticsIAView."""

    def setUp(self):
        self.staff_user = create_user(email="staff@test.com", is_staff=True)
        create_trade(self.staff_user)

    @patch("trades.llm_service.run_global_analytics_llm")
    def test_exibe_mensagem_amigavel_quando_llm_falha(self, mock_run):
        mock_run.side_effect = AnalyticsLLMError("Erro na API")
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse("trades:analytics_ia_global"))
        self.assertEqual(response.status_code, 302)
        run = GlobalAIAnalyticsRun.objects.order_by("-requested_at").first()
        self.assertIn("Erro na geração do relatório", run.result)
