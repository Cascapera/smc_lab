from __future__ import annotations

import mimetypes
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, ExtractHour
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views import View
from django.views.generic import CreateView, TemplateView, UpdateView

from accounts.mixins import PlanRequiredMixin, StaffRequiredMixin
from accounts.models import Plan

from .analytics import (
    _aggregate_by,
    compute_advanced_metrics,
    compute_drawdown_series,
    compute_global_dashboard,
    compute_user_dashboard,
)
from .forms import TradeForm
from .llm_service import AnalyticsLLMError
from .models import (
    AIAnalyticsRun,
    AIRunStatus,
    Direction,
    EntryType,
    GlobalAIAnalyticsRun,
    HighTimeFrame,
    Market,
    PartialTrade,
    RegionHTF,
    ResultType,
    Setup,
    SMCPanel,
    Trade,
    Trend,
    Trigger,
)
from .services.analytics_ia import montar_contexto as montar_contexto_da_ia
from .tasks import run_ai_analysis


def _safe_next_url(request, candidate: str | None, fallback: str = "trades:dashboard") -> str:
    """
    Valida um destino vindo do usuário (?next=, campo next ou Referer).

    Sem essa checagem, `?next=https://site-malicioso/` faz a aplicação redirecionar
    para fora do domínio depois de salvar/excluir um trade (open redirect), o que
    dá credibilidade a páginas de phishing. Só aceitamos destinos do próprio host.
    """
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(fallback)


def _avisar_incoerencias(request, form) -> None:
    """
    Mostra as contradições detectadas no formulário, sem impedir o registro.

    Os relatórios usam `result_type` para o win rate e o SINAL de
    `profit_amount` para streaks e profit factor: quando discordam, as métricas
    deixam de ser comparáveis. O usuário precisa saber, mesmo que o registro
    seja intencional.
    """
    for aviso in getattr(form, "avisos", []) or []:
        messages.warning(request, f"Atenção: {aviso}")


def _mural_display_name(trade: Trade) -> str:
    """Primeiro nome do usuário ou 'Anônimo' conforme preferência do trade."""
    if trade.display_as_anonymous:
        return "Anônimo"
    name = trade.user.first_name or (trade.user.get_full_name() or "").strip()
    if name:
        return name.split()[0] if name.split() else "Anônimo"
    return "Anônimo"


class TradeCreateView(LoginRequiredMixin, CreateView):
    model = Trade
    form_class = TradeForm
    template_name = "trades/trade_form.html"
    success_url = reverse_lazy("trades:trade_add")

    def form_valid(self, form: TradeForm):
        trade: Trade = form.save(commit=False)
        trade.user = self.request.user

        executed_at = form.cleaned_data["executed_at"]
        if timezone.is_naive(executed_at):
            executed_at = timezone.make_aware(executed_at, timezone.get_current_timezone())
        trade.executed_at = executed_at

        trade.save()
        self.object = trade  # necessário para get_success_url do CreateView
        messages.success(self.request, "Operação registrada com sucesso!")
        _avisar_incoerencias(self.request, form)
        return redirect(self.get_success_url())

    def form_invalid(self, form: TradeForm):
        messages.error(self.request, "Verifique os erros no formulário.")
        return super().form_invalid(form)

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("executed_at", timezone.localtime().replace(microsecond=0))
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = _safe_next_url(
            self.request,
            self.request.GET.get("next") or self.request.META.get("HTTP_REFERER"),
        )
        return context


class TradeUpdateView(LoginRequiredMixin, UpdateView):
    model = Trade
    form_class = TradeForm
    template_name = "trades/trade_form.html"

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user)

    def form_valid(self, form: TradeForm):
        trade: Trade = form.save(commit=False)
        trade.user = self.request.user

        executed_at = form.cleaned_data["executed_at"]
        if timezone.is_naive(executed_at):
            executed_at = timezone.make_aware(executed_at, timezone.get_current_timezone())
        trade.executed_at = executed_at

        trade.save()
        self.object = trade
        messages.success(self.request, "Operação atualizada com sucesso!")
        _avisar_incoerencias(self.request, form)
        return redirect(self.get_success_url())

    def form_invalid(self, form: TradeForm):
        messages.error(self.request, "Verifique os erros no formulário.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = _safe_next_url(
            self.request,
            self.request.GET.get("next") or self.request.META.get("HTTP_REFERER"),
        )
        return context

    def get_success_url(self):
        return _safe_next_url(self.request, self.request.GET.get("next"))


class TradeDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk: int):
        trade = get_object_or_404(Trade, pk=pk, user=request.user)
        trade.delete()
        messages.success(request, "Operação removida com sucesso!")
        next_url = _safe_next_url(
            request, request.POST.get("next") or request.META.get("HTTP_REFERER")
        )
        return redirect(next_url)


class TradeScreenshotView(View):
    """
    Exibe a captura do trade. Dono sempre pode ver; trade público (mural) qualquer um pode ver;
    membros da equipe (is_staff) podem ver qualquer captura.
    """

    def get(self, request, pk: int):
        trade = get_object_or_404(Trade, pk=pk)
        if not trade.screenshot:
            raise Http404("Captura não encontrada.")
        is_owner = request.user.is_authenticated and trade.user_id == request.user.id
        is_staff = getattr(request.user, "is_staff", False) or getattr(
            request.user, "is_superuser", False
        )
        if not is_owner and not trade.is_public and not is_staff:
            raise Http404("Captura não encontrada.")
        try:
            screenshot_file = trade.screenshot.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            raise Http404("Captura não encontrada.")
        content_type, _ = mimetypes.guess_type(trade.screenshot.name) or ("image/jpeg",)
        return FileResponse(
            screenshot_file,
            as_attachment=False,
            content_type=content_type,
        )


class MuralView(TemplateView):
    """Mural público: últimos 40 trades com imagem, is_public e usuário Basic+."""

    template_name = "trades/mural.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        qs = (
            Trade.objects.filter(is_public=True)
            .exclude(screenshot="")
            .filter(
                Q(user__profile__plan__in=[Plan.BASIC, Plan.PREMIUM, Plan.PREMIUM_PLUS]),
                Q(user__profile__plan_expires_at__isnull=True)
                | Q(user__profile__plan_expires_at__gt=now),
            )
            .select_related("user")
            .order_by("-executed_at", "-id")[:40]
        )
        context["mural_trades"] = [{"trade": t, "display_name": _mural_display_name(t)} for t in qs]
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "trades/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = compute_user_dashboard(self.request.user)
        context["dashboard"] = dashboard

        balance_series = dashboard["balance_series"]
        result_distribution = dashboard["result_distribution"]

        context["balance_chart"] = {
            "labels": [point["date"] for point in balance_series],
            "dataset": [point["balance"] for point in balance_series],
        }
        context["result_chart"] = {
            "labels": [item["label"] for item in result_distribution],
            "dataset": [item["count"] for item in result_distribution],
        }
        balance_paginator = Paginator(balance_series, 10)
        balance_page_number = self.request.GET.get("balance_page")
        context["balance_page"] = balance_paginator.get_page(balance_page_number)

        # Lista de trades com filtros
        trades_qs = Trade.objects.filter(user=self.request.user)
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.last_reset_at:
            trades_qs = trades_qs.filter(executed_at__gte=profile.last_reset_at)

        selected_filters = {
            "market": self.request.GET.get("market") or "",
            "setup": self.request.GET.get("setup") or "",
            "entry_type": self.request.GET.get("entry_type") or "",
            "result_type": self.request.GET.get("result_type") or "",
            "symbol": self.request.GET.get("symbol") or "",
        }

        if selected_filters["market"]:
            trades_qs = trades_qs.filter(market=selected_filters["market"])
        if selected_filters["setup"]:
            trades_qs = trades_qs.filter(setup=selected_filters["setup"])
        if selected_filters["entry_type"]:
            trades_qs = trades_qs.filter(entry_type=selected_filters["entry_type"])
        if selected_filters["result_type"]:
            trades_qs = trades_qs.filter(result_type=selected_filters["result_type"])
        if selected_filters["symbol"]:
            trades_qs = trades_qs.filter(symbol__icontains=selected_filters["symbol"])

        trades_qs = trades_qs.order_by("-executed_at")

        trades_paginator = Paginator(trades_qs, 10)
        trades_page_number = self.request.GET.get("trade_page")
        context["trades_page"] = trades_paginator.get_page(trades_page_number)

        context["trade_filters"] = selected_filters
        context["trade_choices"] = {
            "markets": Market.choices,
            "setups": Setup.choices,
            "entry_types": EntryType.choices,
            "result_types": ResultType.choices,
        }
        return context


# Espera curta depois de uma falha da IA. Uma falha não consome a análise da
# semana, mas sem nenhum limite um erro de integração (chave inválida, cota
# estourada) permitiria martelar a OpenAI a cada clique.
AI_FAILURE_COOLDOWN = timedelta(minutes=10)


def _can_request_ai_analysis(user):
    """
    Verifica se o usuário pode solicitar nova análise por IA.
    Só pode quando: (1) passaram 7+ dias desde a última análise **bem-sucedida**
    e (2) existe pelo menos 1 trade novo desde essa análise.
    Administradores (is_staff ou is_superuser) não têm limite semanal.

    Só execuções com status `success` contam. Antes, o critério era "tem texto
    em result" e o texto de erro era gravado ali: uma indisponibilidade da
    OpenAI bloqueava o assinante por 7 dias e ainda exibia a mensagem de erro
    como se fosse o resumo da IA.

    Retorna (pode_solicitar, proxima_disponivel_em, ultima_execucao_ok,
             tem_trades_novos, seven_days_passed).
    """
    runs = AIAnalyticsRun.objects.filter(user=user)
    last_success = runs.filter(status=AIRunStatus.SUCCESS).order_by("-requested_at").first()

    # Falha recente: segura por alguns minutos, sem queimar a análise da semana.
    last_failure = runs.filter(status=AIRunStatus.FAILED).order_by("-requested_at").first()
    if last_failure:
        retry_at = last_failure.requested_at + AI_FAILURE_COOLDOWN
        if retry_at > timezone.now():
            return False, retry_at, last_success, True, True

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True, None, last_success, True, True

    from django.conf import settings

    ref_run = last_success

    seven_days_passed = ref_run is None or (
        ref_run.requested_at + timedelta(days=7) <= timezone.now()
    )
    # `created_at`, nao `executed_at`: a data de execucao e digitada pelo usuario.
    # Quem registrava hoje 10 trades da semana passada (backfill) via
    # "Registre pelo menos um novo trade", e um trade com data futura satisfazia
    # o gate sem nada ter acontecido.
    has_new_trades = (
        ref_run is None
        or Trade.objects.filter(user=user, created_at__gt=ref_run.requested_at).exists()
    )

    # T10: analise sobre pouquissimos trades gasta uma chamada paga e queima a
    # semana do assinante para produzir um relatorio sem substancia.
    minimo = int(getattr(settings, "AI_ANALYSIS_MIN_TRADES", 10))
    total_de_trades = Trade.objects.filter(user=user).count()
    if total_de_trades < minimo:
        return False, None, last_success, has_new_trades, seven_days_passed

    can_request = seven_days_passed and has_new_trades
    next_available = None
    if ref_run and not can_request:
        next_available = ref_run.requested_at + timedelta(days=7)

    return can_request, next_available, last_success, has_new_trades, seven_days_passed


class AdvancedDashboardView(PlanRequiredMixin, TemplateView):
    template_name = "trades/dashboard_advanced.html"
    required_plan = Plan.PREMIUM

    def get_insufficient_message(self):
        return mark_safe(
            "O Dashboard Avançado é exclusivo para o plano Premium. "
            f'Assine em <a href="{reverse("payments:plans")}">Planos</a> '
            "ou entre em contato pelo "
            '<a href="https://wa.me/5511975743767" target="_blank" rel="noopener">WhatsApp</a>.'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = compute_user_dashboard(self.request.user)
        context["dashboard"] = base

        trades_qs = Trade.objects.filter(user=self.request.user).order_by("executed_at")
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.last_reset_at:
            trades_qs = trades_qs.filter(executed_at__gte=profile.last_reset_at)

        balance_series = base.get("balance_series", [])
        initial_balance = base["summary"]["initial_balance"]
        advanced = compute_advanced_metrics(
            trades_qs, balance_series, initial_balance, base["summary"]
        )
        dd_series, _, _ = compute_drawdown_series(balance_series, initial_balance)

        context["advanced"] = advanced
        context["advanced_chart"] = {
            "labels": [point["date"] for point in balance_series],
            "balance": [point["balance"] for point in balance_series],
            "drawdown": dd_series,
        }

        # Reaproveita tabelas por mercado/setup/entrada (já com Result/ Técnico)
        context["by_market"] = base.get("by_market", [])
        context["by_setup"] = base.get("by_setup", [])
        context["by_entry_type"] = base.get("by_entry_type", [])

        # Tabelas por HTF, tendência, painel SMC, região HTF e gatilho
        context["by_htf"] = _aggregate_by(trades_qs, "high_time_frame", dict(HighTimeFrame.choices))
        context["by_trend"] = _aggregate_by(trades_qs, "trend", dict(Trend.choices))
        context["by_smc_panel"] = _aggregate_by(trades_qs, "smc_panel", dict(SMCPanel.choices))
        context["by_region_htf"] = _aggregate_by(trades_qs, "region_htf", dict(RegionHTF.choices))
        context["by_trigger"] = _aggregate_by(trades_qs, "trigger", dict(Trigger.choices))

        # Lista de trades com filtros avançados
        table_qs = Trade.objects.filter(user=self.request.user)
        if profile and profile.last_reset_at:
            table_qs = table_qs.filter(executed_at__gte=profile.last_reset_at)

        selected_filters = {
            "market": self.request.GET.get("market") or "",
            "setup": self.request.GET.get("setup") or "",
            "entry_type": self.request.GET.get("entry_type") or "",
            "result_type": self.request.GET.get("result_type") or "",
            "direction": self.request.GET.get("direction") or "",
            "high_time_frame": self.request.GET.get("high_time_frame") or "",
            "region_htf": self.request.GET.get("region_htf") or "",
            "trend": self.request.GET.get("trend") or "",
            "smc_panel": self.request.GET.get("smc_panel") or "",
            "trigger": self.request.GET.get("trigger") or "",
            "partial_trade": self.request.GET.get("partial_trade") or "",
            "symbol": self.request.GET.get("symbol") or "",
        }

        if selected_filters["market"]:
            table_qs = table_qs.filter(market=selected_filters["market"])
        if selected_filters["setup"]:
            table_qs = table_qs.filter(setup=selected_filters["setup"])
        if selected_filters["entry_type"]:
            table_qs = table_qs.filter(entry_type=selected_filters["entry_type"])
        if selected_filters["result_type"]:
            table_qs = table_qs.filter(result_type=selected_filters["result_type"])
        if selected_filters["direction"]:
            table_qs = table_qs.filter(direction=selected_filters["direction"])
        if selected_filters["high_time_frame"]:
            table_qs = table_qs.filter(high_time_frame=selected_filters["high_time_frame"])
        if selected_filters["region_htf"]:
            table_qs = table_qs.filter(region_htf=selected_filters["region_htf"])
        if selected_filters["trend"]:
            table_qs = table_qs.filter(trend=selected_filters["trend"])
        if selected_filters["smc_panel"]:
            table_qs = table_qs.filter(smc_panel=selected_filters["smc_panel"])
        if selected_filters["trigger"]:
            table_qs = table_qs.filter(trigger=selected_filters["trigger"])
        if selected_filters["partial_trade"]:
            table_qs = table_qs.filter(partial_trade=selected_filters["partial_trade"])
        if selected_filters["symbol"]:
            table_qs = table_qs.filter(symbol__icontains=selected_filters["symbol"])

        table_qs = table_qs.order_by("-executed_at")

        trades_paginator = Paginator(table_qs, 12)
        trades_page_number = self.request.GET.get("trade_page")
        trades_page = trades_paginator.get_page(trades_page_number)

        filters_qs = self.request.GET.copy()
        if "trade_page" in filters_qs:
            filters_qs.pop("trade_page")

        context["adv_trades_page"] = trades_page
        context["adv_trade_filters"] = selected_filters
        context["adv_filters_query"] = filters_qs.urlencode()
        context["adv_trade_choices"] = {
            "markets": Market.choices,
            "setups": Setup.choices,
            "entry_types": EntryType.choices,
            "result_types": ResultType.choices,
            "directions": Direction.choices,
            "high_time_frames": HighTimeFrame.choices,
            "region_htfs": RegionHTF.choices,
            "trends": Trend.choices,
            "smc_panels": SMCPanel.choices,
            "triggers": Trigger.choices,
            "partial_trades": PartialTrade.choices,
        }

        return context


class AnalyticsIAView(PlanRequiredMixin, TemplateView):
    """
    Analytics avançado por IA. Apenas Premium/Premium+.
    Limite: 1 solicitação por semana por usuário.
    Métricas são pré-calculadas; a IA responde apenas a perguntas específicas (economia de tokens).
    """

    template_name = "trades/analytics_ia.html"
    required_plan = Plan.PREMIUM

    def get_insufficient_message(self):
        return mark_safe(
            "A análise por IA é exclusiva para planos Premium e Premium+. "
            f'Assine em <a href="{reverse("payments:plans")}">Planos</a> '
            "ou entre em contato pelo "
            '<a href="https://wa.me/5511975743767" target="_blank" rel="noopener">WhatsApp</a>.'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Mesmas metricas que a task do Celery usa para montar o prompt.
        dados = montar_contexto_da_ia(user)
        base = dados["dashboard"]
        trades_qs = dados["trades_qs"]
        context.update({chave: valor for chave, valor in dados.items() if chave != "trades_qs"})
        context["by_market"] = base.get("by_market", [])
        context["by_setup"] = base.get("by_setup", [])
        context["by_entry_type"] = base.get("by_entry_type", [])

        # Tabela de trades ordenada por ganho (decrescente) com Ganho/CT e paginação
        trades_for_table = trades_qs.annotate(
            ganho_ct=Case(
                When(
                    market=Market.FOREX,
                    then=F("profit_amount") * Value(Decimal("0.01")) / F("quantity"),
                ),
                default=F("profit_amount") / F("quantity"),
                output_field=DecimalField(),
            )
        ).order_by("-profit_amount")
        paginator_table = Paginator(trades_for_table, 20)
        page_num = self.request.GET.get("analytics_page", 1)
        context["analytics_trades_page"] = paginator_table.get_page(page_num)

        # Gráfico por horário (ganho, perda, lucro por hora)
        hourly = (
            trades_qs.annotate(hour=ExtractHour("executed_at"))
            .values("hour")
            .annotate(
                gain=Coalesce(Sum("profit_amount", filter=Q(profit_amount__gt=0)), Decimal("0")),
                loss=Coalesce(Sum("profit_amount", filter=Q(profit_amount__lt=0)), Decimal("0")),
            )
            .order_by("hour")
        )
        context["chart_hour_data"] = [
            {
                "label": f"{r['hour']:02d}:00",
                "gain": float(r["gain"]),
                "loss": float(r["loss"]),
                "net": float(r["gain"]) + float(r["loss"]),
            }
            for r in hourly
        ]

        # Gráfico por símbolo (até 20 ativos por quantidade de trades)
        symbol_top = (
            trades_qs.values("symbol")
            .annotate(
                n=Count("id"),
                gain=Coalesce(Sum("profit_amount", filter=Q(profit_amount__gt=0)), Decimal("0")),
                loss=Coalesce(Sum("profit_amount", filter=Q(profit_amount__lt=0)), Decimal("0")),
            )
            .order_by("-n")[:20]
        )
        context["chart_symbol_data"] = [
            {
                "label": r["symbol"],
                "gain": float(r["gain"]),
                "loss": float(r["loss"]),
                "net": float(r["gain"]) + float(r["loss"]),
            }
            for r in symbol_top
        ]

        # Gráfico pizza por mercado (5 mercados: ganho, perda, lucro)
        context["chart_market_data"] = []
        for market_value, market_label in Market.choices:
            qs_m = trades_qs.filter(market=market_value)
            agg = qs_m.aggregate(
                gain=Coalesce(Sum("profit_amount", filter=Q(profit_amount__gt=0)), Decimal("0")),
                loss=Coalesce(Sum("profit_amount", filter=Q(profit_amount__lt=0)), Decimal("0")),
            )
            total_m = float(agg["gain"]) + float(agg["loss"])
            context["chart_market_data"].append(
                {
                    "market_label": market_label,
                    "gain": float(agg["gain"]),
                    "loss": abs(float(agg["loss"])),
                    "net": total_m,
                }
            )

        can_request, next_available, last_run, has_new_trades, seven_days_passed = (
            _can_request_ai_analysis(user)
        )
        context["ai_can_request"] = can_request
        context["ai_next_available"] = next_available
        context["ai_last_run"] = last_run
        context["ai_has_new_trades"] = has_new_trades
        context["ai_seven_days_passed"] = seven_days_passed
        context["ai_requested"] = self.request.GET.get("requested") == "1"

        return context

    def post(self, request, *args, **kwargs):
        can_request, next_available, last_run, has_new_trades, seven_days_passed = (
            _can_request_ai_analysis(request.user)
        )
        if not can_request:
            if not has_new_trades:
                messages.warning(
                    request,
                    "Registre pelo menos um novo trade desde a última análise para solicitar uma nova.",
                )
            else:
                messages.warning(
                    request,
                    "Sua próxima análise poderá ser realizada após 7 dias da última.",
                )
            return redirect(reverse("trades:analytics_ia"))

        # Trava por usuario: sem ela, duplo clique ou duas abas passavam os dois
        # pela checagem antes de qualquer `create`, e com 2 workers do gunicorn
        # saiam DUAS chamadas pagas a OpenAI.
        chave_da_trava = f"ai-analysis:{request.user.pk}"
        if not cache.add(chave_da_trava, "1", 300):
            messages.info(request, "Sua analise ja esta sendo gerada. Aguarde alguns instantes.")
            return redirect(reverse("trades:analytics_ia") + "?requested=1")

        run = AIAnalyticsRun.objects.create(user=request.user)

        # A chamada a OpenAI sai do request: leva ate 90s e ocupava metade da
        # capacidade do site (2 workers). `on_commit` porque com ATOMIC_REQUESTS
        # a task sairia antes do commit e nao encontraria a execucao.
        transaction.on_commit(lambda: run_ai_analysis.delay(run.pk))

        messages.info(
            request,
            "Analise solicitada. O resultado aparece nesta pagina assim que ficar pronto.",
        )
        return redirect(reverse("trades:analytics_ia") + "?requested=1")


class AnalyticsIAStatusView(PlanRequiredMixin, View):
    """
    Situação da última análise do usuário, consultada pela página enquanto a
    task roda em background.

    Devolve JSON porque é consumida por fetch(): um redirect de HTML quebraria o
    polling. Só expõe a execução do próprio usuário logado.
    """

    required_plan = Plan.PREMIUM

    def get(self, request, *args, **kwargs):
        run = AIAnalyticsRun.objects.filter(user=request.user).order_by("-requested_at").first()
        if run is None:
            return JsonResponse({"status": "none"})

        return JsonResponse(
            {
                "status": run.status,
                "pronta": run.status == AIRunStatus.SUCCESS,
                "falhou": run.status == AIRunStatus.FAILED,
                "solicitada_em": run.requested_at.isoformat(),
            }
        )


class GlobalDashboardView(StaffRequiredMixin, TemplateView):
    """
    Dashboard global: todos os trades de todos os usuários.
    Acesso restrito à equipe (is_staff). Não exibe nome do trader.
    """

    template_name = "trades/dashboard_global.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trades_qs = Trade.objects.all().order_by("executed_at")
        base = compute_global_dashboard(trades_qs)
        context["dashboard"] = base

        balance_series = base.get("balance_series", [])
        initial_balance = Decimal("0")
        advanced = compute_advanced_metrics(
            trades_qs, balance_series, initial_balance, base["summary"]
        )
        dd_series, _, _ = compute_drawdown_series(balance_series, initial_balance)

        context["advanced"] = advanced
        context["advanced_chart"] = {
            "labels": [point["date"] for point in balance_series],
            "balance": [point["balance"] for point in balance_series],
            "drawdown": dd_series,
        }

        context["by_market"] = base.get("by_market", [])
        context["by_setup"] = base.get("by_setup", [])
        context["by_entry_type"] = base.get("by_entry_type", [])
        context["by_htf"] = _aggregate_by(trades_qs, "high_time_frame", dict(HighTimeFrame.choices))
        context["by_trend"] = _aggregate_by(trades_qs, "trend", dict(Trend.choices))
        context["by_smc_panel"] = _aggregate_by(trades_qs, "smc_panel", dict(SMCPanel.choices))
        context["by_region_htf"] = _aggregate_by(trades_qs, "region_htf", dict(RegionHTF.choices))
        context["by_trigger"] = _aggregate_by(trades_qs, "trigger", dict(Trigger.choices))

        table_qs = Trade.objects.all()
        selected_filters = {
            "market": self.request.GET.get("market") or "",
            "setup": self.request.GET.get("setup") or "",
            "entry_type": self.request.GET.get("entry_type") or "",
            "result_type": self.request.GET.get("result_type") or "",
            "direction": self.request.GET.get("direction") or "",
            "high_time_frame": self.request.GET.get("high_time_frame") or "",
            "region_htf": self.request.GET.get("region_htf") or "",
            "trend": self.request.GET.get("trend") or "",
            "smc_panel": self.request.GET.get("smc_panel") or "",
            "trigger": self.request.GET.get("trigger") or "",
            "partial_trade": self.request.GET.get("partial_trade") or "",
            "symbol": self.request.GET.get("symbol") or "",
        }
        if selected_filters["market"]:
            table_qs = table_qs.filter(market=selected_filters["market"])
        if selected_filters["setup"]:
            table_qs = table_qs.filter(setup=selected_filters["setup"])
        if selected_filters["entry_type"]:
            table_qs = table_qs.filter(entry_type=selected_filters["entry_type"])
        if selected_filters["result_type"]:
            table_qs = table_qs.filter(result_type=selected_filters["result_type"])
        if selected_filters["direction"]:
            table_qs = table_qs.filter(direction=selected_filters["direction"])
        if selected_filters["high_time_frame"]:
            table_qs = table_qs.filter(high_time_frame=selected_filters["high_time_frame"])
        if selected_filters["region_htf"]:
            table_qs = table_qs.filter(region_htf=selected_filters["region_htf"])
        if selected_filters["trend"]:
            table_qs = table_qs.filter(trend=selected_filters["trend"])
        if selected_filters["smc_panel"]:
            table_qs = table_qs.filter(smc_panel=selected_filters["smc_panel"])
        if selected_filters["trigger"]:
            table_qs = table_qs.filter(trigger=selected_filters["trigger"])
        if selected_filters["partial_trade"]:
            table_qs = table_qs.filter(partial_trade=selected_filters["partial_trade"])
        if selected_filters["symbol"]:
            table_qs = table_qs.filter(symbol__icontains=selected_filters["symbol"])

        table_qs = table_qs.order_by("-executed_at")
        trades_paginator = Paginator(table_qs, 12)
        trades_page_number = self.request.GET.get("trade_page")
        trades_page = trades_paginator.get_page(trades_page_number)

        filters_qs = self.request.GET.copy()
        if "trade_page" in filters_qs:
            filters_qs.pop("trade_page")

        context["adv_trades_page"] = trades_page
        context["adv_trade_filters"] = selected_filters
        context["adv_filters_query"] = filters_qs.urlencode()
        context["adv_trade_choices"] = {
            "markets": Market.choices,
            "setups": Setup.choices,
            "entry_types": EntryType.choices,
            "result_types": ResultType.choices,
            "directions": Direction.choices,
            "high_time_frames": HighTimeFrame.choices,
            "region_htfs": RegionHTF.choices,
            "trends": Trend.choices,
            "smc_panels": SMCPanel.choices,
            "triggers": Trigger.choices,
            "partial_trades": PartialTrade.choices,
        }
        context["is_global"] = True
        return context


def _can_request_global_ai_analysis(user):
    """Verifica se staff pode solicitar nova análise global. Limite: 1x por semana."""
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        return False, None, None, False, False

    last_failure = (
        GlobalAIAnalyticsRun.objects.filter(status=AIRunStatus.FAILED)
        .order_by("-requested_at")
        .first()
    )
    last_run = (
        GlobalAIAnalyticsRun.objects.filter(status=AIRunStatus.SUCCESS)
        .order_by("-requested_at")
        .first()
    )
    if last_failure:
        retry_at = last_failure.requested_at + AI_FAILURE_COOLDOWN
        if retry_at > timezone.now():
            return False, retry_at, last_run, True, True

    seven_days_passed = last_run is None or (
        last_run.requested_at + timedelta(days=7) <= timezone.now()
    )
    all_trades = Trade.objects.all()
    has_new_trades = (
        last_run is None or all_trades.filter(executed_at__gt=last_run.requested_at).exists()
    )

    can_request = seven_days_passed and has_new_trades
    next_available = (
        (last_run.requested_at + timedelta(days=7)) if last_run and not seven_days_passed else None
    )
    return can_request, next_available, last_run, has_new_trades, seven_days_passed


class GlobalAnalyticsIAView(StaffRequiredMixin, TemplateView):
    """
    Análise por IA do dashboard global. Apenas equipe.
    """

    template_name = "trades/analytics_ia_global.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trades_qs = Trade.objects.all().order_by("executed_at")
        base = compute_global_dashboard(trades_qs)
        context["dashboard"] = base

        balance_series = base.get("balance_series", [])
        initial_balance = Decimal("0")
        context["advanced"] = compute_advanced_metrics(
            trades_qs, balance_series, initial_balance, base["summary"]
        )
        context["by_market"] = base.get("by_market", [])
        context["by_setup"] = base.get("by_setup", [])
        context["by_entry_type"] = base.get("by_entry_type", [])

        combo_fields = [
            "setup",
            "entry_type",
            "high_time_frame",
            "region_htf",
            "trend",
            "smc_panel",
            "trigger",
            "partial_trade",
        ]
        choice_maps = {
            "setup": dict(Setup.choices),
            "entry_type": dict(EntryType.choices),
            "high_time_frame": dict(HighTimeFrame.choices),
            "region_htf": dict(RegionHTF.choices),
            "trend": dict(Trend.choices),
            "smc_panel": dict(SMCPanel.choices),
            "trigger": dict(Trigger.choices),
            "partial_trade": dict(PartialTrade.choices),
        }

        combos = (
            trades_qs.values(*combo_fields)
            .annotate(total=Coalesce(Sum("profit_amount"), Decimal("0")))
            .order_by("-total")
        )
        top3_best_raw = list(combos[:3])
        top3_worst_raw = list(
            trades_qs.values(*combo_fields)
            .annotate(total=Coalesce(Sum("profit_amount"), Decimal("0")))
            .order_by("total")[:3]
        )

        def _combo_rows(raw_list):
            return [
                {
                    **{f: row[f] for f in combo_fields},
                    "total": row["total"],
                    "labels": {
                        f: choice_maps[f].get(row[f], row[f] or "N/D") for f in combo_fields
                    },
                }
                for row in raw_list
            ]

        context["top3_best_combos"] = _combo_rows(top3_best_raw)
        context["top3_worst_combos"] = _combo_rows(top3_worst_raw)

        total_profit = base["summary"]["total_profit"]
        sum_worst = sum(float(r["total"]) for r in top3_worst_raw)
        improvement_reais = abs(min(0, sum_worst))
        improvement_new_total = float(total_profit) + improvement_reais
        denom = abs(float(total_profit)) if total_profit else 1
        improvement_pct = round(improvement_reais / denom * 100, 2) if denom else 0
        context["improvement_reais"] = round(improvement_reais, 2)
        context["improvement_new_total"] = round(improvement_new_total, 2)
        context["improvement_pct"] = improvement_pct

        trades_for_table = trades_qs.annotate(
            ganho_ct=Case(
                When(
                    market=Market.FOREX,
                    then=F("profit_amount") * Value(Decimal("0.01")) / F("quantity"),
                ),
                default=F("profit_amount") / F("quantity"),
                output_field=DecimalField(),
            )
        ).order_by("-profit_amount")
        paginator_table = Paginator(trades_for_table, 20)
        page_num = self.request.GET.get("analytics_page", 1)
        context["analytics_trades_page"] = paginator_table.get_page(page_num)

        hourly = (
            trades_qs.annotate(hour=ExtractHour("executed_at"))
            .values("hour")
            .annotate(
                gain=Coalesce(Sum("profit_amount", filter=Q(profit_amount__gt=0)), Decimal("0")),
                loss=Coalesce(Sum("profit_amount", filter=Q(profit_amount__lt=0)), Decimal("0")),
            )
            .order_by("hour")
        )
        context["chart_hour_data"] = [
            {
                "label": f"{r['hour']:02d}:00",
                "gain": float(r["gain"]),
                "loss": float(r["loss"]),
                "net": float(r["gain"]) + float(r["loss"]),
            }
            for r in hourly
        ]

        symbol_top = (
            trades_qs.values("symbol")
            .annotate(
                n=Count("id"),
                gain=Coalesce(Sum("profit_amount", filter=Q(profit_amount__gt=0)), Decimal("0")),
                loss=Coalesce(Sum("profit_amount", filter=Q(profit_amount__lt=0)), Decimal("0")),
            )
            .order_by("-n")[:20]
        )
        context["chart_symbol_data"] = [
            {
                "label": r["symbol"],
                "gain": float(r["gain"]),
                "loss": float(r["loss"]),
                "net": float(r["gain"]) + float(r["loss"]),
            }
            for r in symbol_top
        ]

        context["chart_market_data"] = []
        for market_value, market_label in Market.choices:
            qs_m = trades_qs.filter(market=market_value)
            agg = qs_m.aggregate(
                gain=Coalesce(Sum("profit_amount", filter=Q(profit_amount__gt=0)), Decimal("0")),
                loss=Coalesce(Sum("profit_amount", filter=Q(profit_amount__lt=0)), Decimal("0")),
            )
            total_m = float(agg["gain"]) + float(agg["loss"])
            context["chart_market_data"].append(
                {
                    "market_label": market_label,
                    "gain": float(agg["gain"]),
                    "loss": abs(float(agg["loss"])),
                    "net": total_m,
                }
            )

        can_request, next_available, last_run, has_new_trades, seven_days_passed = (
            _can_request_global_ai_analysis(self.request.user)
        )
        context["ai_can_request"] = can_request
        context["ai_next_available"] = next_available
        context["ai_last_run"] = last_run
        context["ai_has_new_trades"] = has_new_trades
        context["ai_seven_days_passed"] = seven_days_passed
        context["ai_requested"] = self.request.GET.get("requested") == "1"
        context["is_global"] = True

        return context

    def post(self, request, *args, **kwargs):
        can_request, next_available, last_run, has_new_trades, seven_days_passed = (
            _can_request_global_ai_analysis(request.user)
        )
        if not can_request:
            if not has_new_trades:
                messages.warning(
                    request,
                    "Registre pelo menos um novo trade na plataforma para solicitar uma nova análise.",
                )
            else:
                messages.warning(
                    request, "A próxima análise poderá ser realizada após 7 dias da última."
                )
            return redirect(reverse("trades:analytics_ia_global"))

        context = self.get_context_data()
        from .llm_service import run_global_analytics_llm

        run = GlobalAIAnalyticsRun.objects.create(requested_by=request.user)
        try:
            result_text = run_global_analytics_llm(context)
            if not (result_text or "").strip():
                raise AnalyticsLLMError("A IA não retornou texto.")
            run.result = result_text
            run.status = AIRunStatus.SUCCESS
            run.save(update_fields=["result", "status"])
            messages.success(request, "Análise global concluída. Veja o resultado abaixo.")
        except AnalyticsLLMError as exc:
            run.status = AIRunStatus.FAILED
            run.error_detail = str(exc)[:2000] or "AnalyticsLLMError"
            run.save(update_fields=["status", "error_detail"])
            messages.warning(
                request,
                "Erro na geração do relatório, desculpe o inconveniente, "
                "tente novamente em alguns minutos.",
            )
        return redirect(reverse("trades:analytics_ia_global") + "?requested=1")
