from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDay

from accounts.models import Profile

from .models import EntryType, Market, ResultType, Setup, Trade


def _aggregate_by(queryset, field: str, display_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
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
    profile, _ = Profile.objects.get_or_create(user=user)

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
        balance_series[-1]["balance"] if balance_series else round(float(profile.current_balance), 2)
    )

    by_market = _aggregate_by(trades, "market", dict(Market.choices))
    by_setup = _aggregate_by(trades, "setup", dict(Setup.choices))
    by_entry = _aggregate_by(trades, "entry_type", dict(EntryType.choices))

    result_distribution = [
        {"label": "Gain", "count": wins, "percentage": round(win_rate, 2)},
        {"label": "Loss", "count": losses, "percentage": round((losses / total_trades * 100) if total_trades else 0, 2)},
        {"label": "Break even", "count": breakevens, "percentage": round((breakevens / total_trades * 100) if total_trades else 0, 2)},
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

