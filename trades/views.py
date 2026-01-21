from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Avg, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, TemplateView

from accounts.mixins import PlanRequiredMixin
from django.utils.safestring import mark_safe
from accounts.models import Plan
from .analytics import compute_user_dashboard
from .forms import TradeForm
from .models import (
    EntryType,
    Market,
    ResultType,
    Setup,
    Trade,
    Direction,
    HighTimeFrame,
    RegionHTF,
    SMCPanel,
    Trend,
    Trigger,
    PartialTrade,
)


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
        return redirect(self.get_success_url())

    def form_invalid(self, form: TradeForm):
        messages.error(self.request, "Verifique os erros no formulário.")
        return super().form_invalid(form)

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("executed_at", timezone.localtime().replace(microsecond=0))
        return initial


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


class AdvancedDashboardView(PlanRequiredMixin, TemplateView):
    template_name = "trades/dashboard_advanced.html"
    required_plan = Plan.PREMIUM
    insufficient_message = mark_safe(
        "O Dashboard Avançado é exclusivo para o plano Premium. "
        'Para contratar o Premium, entre em contato pelo '
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

        gains = trades_qs.filter(profit_amount__gt=0)
        losses = trades_qs.filter(profit_amount__lt=0)
        gross_gain = gains.aggregate(total=Coalesce(Sum("profit_amount"), Decimal("0")))["total"]
        gross_loss = losses.aggregate(total=Coalesce(Sum("profit_amount"), Decimal("0")))["total"]
        avg_gain = gains.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
        avg_loss = losses.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]

        profit_factor = float(gross_gain) / abs(float(gross_loss)) if gross_loss and float(gross_loss) != 0 else None
        payoff = float(avg_gain) / abs(float(avg_loss)) if avg_loss and float(avg_loss) != 0 else None

        # Streaks
        longest_win = longest_loss = current_win = current_loss = 0
        for trade in trades_qs:
            if trade.profit_amount > 0:
                current_win += 1
                current_loss = 0
            elif trade.profit_amount < 0:
                current_loss += 1
                current_win = 0
            else:
                current_win = 0
                current_loss = 0
            longest_win = max(longest_win, current_win)
            longest_loss = max(longest_loss, current_loss)

        # Drawdown
        balance_series = base.get("balance_series", [])
        peak = Decimal(str(base["summary"]["initial_balance"]))
        dd_series = []
        max_dd = Decimal("0")
        max_dd_pct = Decimal("0")
        for point in balance_series:
            bal = Decimal(str(point["balance"]))
            peak = max(peak, bal)
            dd = bal - peak
            dd_pct = (dd / peak * 100) if peak else Decimal("0")
            if dd < max_dd:
                max_dd = dd
            if dd_pct < max_dd_pct:
                max_dd_pct = dd_pct
            dd_series.append(float(dd))

        context["advanced"] = {
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else "N/D",
            "payoff": round(payoff, 2) if payoff is not None else "N/D",
            "max_drawdown": round(float(max_dd), 2),
            "max_drawdown_pct": round(float(max_dd_pct), 2),
            "longest_win_streak": longest_win,
            "longest_loss_streak": longest_loss,
            "avg_gain": round(float(avg_gain), 2),
            "avg_loss": round(float(avg_loss), 2),
            "best_trade": base["summary"]["best_trade"],
            "worst_trade": base["summary"]["worst_trade"],
            "total_trades": base["summary"]["total_trades"],
            "win_rate": base["summary"]["win_rate"],
            "total_profit": base["summary"]["total_profit"],
        }

        context["advanced_chart"] = {
            "labels": [point["date"] for point in balance_series],
            "balance": [point["balance"] for point in balance_series],
            "drawdown": dd_series,
        }

        # Reaproveita tabelas por mercado/setup/entrada
        context["by_market"] = base.get("by_market", [])
        context["by_setup"] = base.get("by_setup", [])
        context["by_entry_type"] = base.get("by_entry_type", [])

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
