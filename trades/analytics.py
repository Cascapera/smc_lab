from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDay

from .models import EntryType, Market, ResultType, Setup, Trade


def compute_global_dashboard(trades_qs) -> dict[str, Any]:
    """
    Calcula métricas agregadas para todos os trades (dashboard global).
    trades_qs: queryset de Trade (ex: Trade.objects.all()).
    Não usa last_reset_at nem saldo por usuário.
    """
    trades = trades_qs.order_by("executed_at")
    total_trades = trades.count()

    if not total_trades:
        return {
            "summary": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "avg_profit": 0.0,
                "avg_gain": 0.0,
                "avg_loss": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "initial_balance": 0.0,
            },
            "balance_series": [],
            "by_market": [],
            "by_setup": [],
            "by_entry_type": [],
            "result_distribution": [],
        }

    wins = trades.filter(result_type=ResultType.GAIN).count()
    losses = trades.filter(result_type=ResultType.LOSS).count()
    breakevens = trades.filter(result_type=ResultType.BREAK_EVEN).count()
    total_profit = trades.aggregate(total=Coalesce(Sum("profit_amount"), Decimal("0")))["total"]
    avg_profit = trades.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    win_rate = (wins / total_trades * 100) if total_trades else 0

    gains_qs = trades.filter(profit_amount__gt=0)
    losses_qs = trades.filter(profit_amount__lt=0)

    avg_gain = gains_qs.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    avg_loss = losses_qs.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    best_trade = trades.aggregate(best=Coalesce(Max("profit_amount"), Decimal("0")))["best"]
    worst_trade = trades.aggregate(worst=Coalesce(Min("profit_amount"), Decimal("0")))["worst"]

    daily = (
        trades.annotate(day=TruncDay("executed_at"))
        .values("day")
        .annotate(profit=Coalesce(Sum("profit_amount"), Decimal("0")))
        .order_by("day")
    )

    running_balance = Decimal("0")
    balance_series = []
    for entry in daily:
        running_balance += entry["profit"]
        balance_series.append(
            {
                "date": entry["day"].date().isoformat(),
                "balance": round(float(running_balance), 2),
                "daily_profit": round(float(entry["profit"]), 2),
            }
        )

    by_market = _aggregate_by(trades, "market", dict(Market.choices))
    by_setup = _aggregate_by(trades, "setup", dict(Setup.choices))
    by_entry = _aggregate_by(trades, "entry_type", dict(EntryType.choices))

    result_distribution = [
        {"label": "Gain", "count": wins, "percentage": round(win_rate, 2)},
        {
            "label": "Loss",
            "count": losses,
            "percentage": round((losses / total_trades * 100) if total_trades else 0, 2),
        },
        {
            "label": "Break even",
            "count": breakevens,
            "percentage": round((breakevens / total_trades * 100) if total_trades else 0, 2),
        },
    ]

    return {
        "summary": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_rate": round(win_rate, 2),
            "total_profit": round(float(total_profit), 2),
            "avg_profit": round(float(avg_profit), 2),
            "avg_gain": round(float(avg_gain), 2),
            "avg_loss": round(float(avg_loss), 2),
            "best_trade": round(float(best_trade), 2),
            "worst_trade": round(float(worst_trade), 2),
            "initial_balance": 0.0,
            "current_balance": round(float(running_balance), 2) if balance_series else 0.0,
        },
        "balance_series": balance_series,
        "by_market": by_market,
        "by_setup": by_setup,
        "by_entry_type": by_entry,
        "result_distribution": result_distribution,
    }


def compute_streaks(profit_amounts) -> tuple[int, int]:
    """
    Calcula longest_win_streak e longest_loss_streak a partir de iterável de profit_amount.
    Retorna (longest_win, longest_loss).
    """
    longest_win = longest_loss = current_win = current_loss = 0
    for amount in profit_amounts:
        if amount > 0:
            current_win += 1
            current_loss = 0
        elif amount < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = 0
            current_loss = 0
        longest_win = max(longest_win, current_win)
        longest_loss = max(longest_loss, current_loss)
    return longest_win, longest_loss


def compute_profit_factor_payoff(
    gross_gain: Decimal,
    gross_loss: Decimal,
    avg_gain: Decimal,
    avg_loss: Decimal,
) -> tuple[float | None, float | None]:
    """Retorna (profit_factor, payoff) ou (None, None) quando não aplicável."""
    profit_factor = (
        float(gross_gain) / abs(float(gross_loss))
        if gross_loss and float(gross_loss) != 0
        else None
    )
    payoff = float(avg_gain) / abs(float(avg_loss)) if avg_loss and float(avg_loss) != 0 else None
    return profit_factor, payoff


def compute_drawdown_series(
    balance_series: list[dict],
    initial_balance: Decimal | float,
) -> tuple[list[float], Decimal, Decimal]:
    """
    Calcula série de drawdown, max_drawdown e max_drawdown_pct.
    Retorna (dd_series, max_dd, max_dd_pct).
    """
    peak = Decimal(str(initial_balance))
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
    return dd_series, max_dd, max_dd_pct


def compute_advanced_metrics(
    trades_qs,
    balance_series: list[dict],
    initial_balance: Decimal | float,
    base_summary: dict,
) -> dict[str, Any]:
    """
    Calcula métricas avançadas: profit_factor, payoff, streaks, drawdown.
    trades_qs: queryset ordenado por executed_at.
    balance_series: do compute_user_dashboard ou compute_global_dashboard.
    base_summary: summary do dashboard base.
    """
    gains = trades_qs.filter(profit_amount__gt=0)
    losses = trades_qs.filter(profit_amount__lt=0)
    gross_gain = gains.aggregate(total=Coalesce(Sum("profit_amount"), Decimal("0")))["total"]
    gross_loss = losses.aggregate(total=Coalesce(Sum("profit_amount"), Decimal("0")))["total"]
    avg_gain = gains.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    avg_loss = losses.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]

    profit_factor, payoff = compute_profit_factor_payoff(gross_gain, gross_loss, avg_gain, avg_loss)
    longest_win, longest_loss = compute_streaks(trades_qs.values_list("profit_amount", flat=True))
    dd_series, max_dd, max_dd_pct = compute_drawdown_series(balance_series, initial_balance)

    return {
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else "N/D",
        "payoff": round(payoff, 2) if payoff is not None else "N/D",
        "max_drawdown": round(float(max_dd), 2),
        "max_drawdown_pct": round(float(max_dd_pct), 2),
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "avg_gain": round(float(avg_gain), 2),
        "avg_loss": round(float(avg_loss), 2),
        "best_trade": base_summary["best_trade"],
        "worst_trade": base_summary["worst_trade"],
        "total_trades": base_summary["total_trades"],
        "win_rate": base_summary["win_rate"],
        "total_profit": base_summary["total_profit"],
    }


def _aggregate_by(
    queryset, field: str, display_map: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    annotated = (
        queryset.values(field)
        .annotate(
            total=Count("id"),
            wins=Count("id", filter=Q(result_type=ResultType.GAIN)),
            losses=Count("id", filter=Q(result_type=ResultType.LOSS)),
            breakevens=Count("id", filter=Q(result_type=ResultType.BREAK_EVEN)),
            total_profit=Coalesce(Sum("profit_amount"), Decimal("0")),
            avg_profit=Coalesce(Avg("profit_amount"), Decimal("0")),
            avg_technical=Coalesce(Avg("technical_gain"), Decimal("0")),
        )
        .order_by("-total")
    )

    data = []
    for row in annotated:
        count = row["total"]
        wins = row["wins"]
        losses = row["losses"]
        breakevens = row["breakevens"]
        win_rate = (wins / count * 100) if count else 0
        raw_value = row.get(field)
        label = display_map.get(raw_value, raw_value) if display_map else raw_value
        if not label:
            label = "N/D"
        avg_profit = row["avg_profit"]
        avg_technical = row["avg_technical"]
        if avg_technical and float(avg_technical) != 0:
            result_vs_technical = round(float(avg_profit) / float(avg_technical) * 100, 2)
        else:
            result_vs_technical = None
        data.append(
            {
                "label": label,
                "count": count,
                "wins": wins,
                "losses": losses,
                "breakevens": breakevens,
                "win_rate": round(win_rate, 2),
                "avg_profit": round(avg_profit, 2),
                "result_vs_technical": result_vs_technical,
            }
        )
    return data


def compute_user_dashboard(user) -> dict[str, Any]:
    profile = user.profile

    trades = Trade.objects.filter(user=user)
    if profile.last_reset_at:
        trades = trades.filter(executed_at__gte=profile.last_reset_at)

    trades = trades.order_by("executed_at")
    total_trades = trades.count()

    if not total_trades:
        return {
            "summary": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "avg_profit": 0.0,
                "avg_gain": 0.0,
                "avg_loss": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "current_balance": float(profile.current_balance),
                "initial_balance": float(profile.initial_balance),
            },
            "balance_series": [],
            "by_market": [],
            "by_setup": [],
            "by_entry_type": [],
            "result_distribution": [],
        }

    wins = trades.filter(result_type=ResultType.GAIN).count()
    losses = trades.filter(result_type=ResultType.LOSS).count()
    breakevens = trades.filter(result_type=ResultType.BREAK_EVEN).count()
    total_profit = trades.aggregate(total=Coalesce(Sum("profit_amount"), Decimal("0")))["total"]
    avg_profit = trades.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    win_rate = (wins / total_trades * 100) if total_trades else 0

    gains_qs = trades.filter(profit_amount__gt=0)
    losses_qs = trades.filter(profit_amount__lt=0)

    avg_gain = gains_qs.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    avg_loss = losses_qs.aggregate(avg=Coalesce(Avg("profit_amount"), Decimal("0")))["avg"]
    best_trade = trades.aggregate(best=Coalesce(Max("profit_amount"), Decimal("0")))["best"]
    worst_trade = trades.aggregate(worst=Coalesce(Min("profit_amount"), Decimal("0")))["worst"]

    daily = (
        trades.annotate(day=TruncDay("executed_at"))
        .values("day")
        .annotate(profit=Coalesce(Sum("profit_amount"), Decimal("0")))
        .order_by("day")
    )

    running_balance = profile.initial_balance
    balance_series = []
    for entry in daily:
        running_balance += entry["profit"]
        balance_series.append(
            {
                "date": entry["day"].date().isoformat(),
                "balance": round(float(running_balance), 2),
                "daily_profit": round(float(entry["profit"]), 2),
            }
        )

    # Se a série foi calculada, usar o último valor como saldo atual calculado
    computed_current_balance = (
        balance_series[-1]["balance"]
        if balance_series
        else round(float(profile.current_balance), 2)
    )

    by_market = _aggregate_by(trades, "market", dict(Market.choices))
    by_setup = _aggregate_by(trades, "setup", dict(Setup.choices))
    by_entry = _aggregate_by(trades, "entry_type", dict(EntryType.choices))

    result_distribution = [
        {"label": "Gain", "count": wins, "percentage": round(win_rate, 2)},
        {
            "label": "Loss",
            "count": losses,
            "percentage": round((losses / total_trades * 100) if total_trades else 0, 2),
        },
        {
            "label": "Break even",
            "count": breakevens,
            "percentage": round((breakevens / total_trades * 100) if total_trades else 0, 2),
        },
    ]

    return {
        "summary": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_rate": round(win_rate, 2),
            "total_profit": round(float(total_profit), 2),
            "avg_profit": round(float(avg_profit), 2),
            "avg_gain": round(float(avg_gain), 2),
            "avg_loss": round(float(avg_loss), 2),
            "best_trade": round(float(best_trade), 2),
            "worst_trade": round(float(worst_trade), 2),
            "current_balance": computed_current_balance,
            "initial_balance": round(float(profile.initial_balance), 2),
        },
        "balance_series": balance_series,
        "by_market": by_market,
        "by_setup": by_setup,
        "by_entry_type": by_entry,
        "result_distribution": result_distribution,
    }
