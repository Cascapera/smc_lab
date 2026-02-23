from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import Profile

from .models import Trade


def _recalculate_profile_balance(user) -> None:
    try:
        profile: Profile = user.profile
    except Profile.DoesNotExist:
        return

    trades_qs = user.trades.all()
    if profile.last_reset_at:
        trades_qs = trades_qs.filter(executed_at__gte=profile.last_reset_at)

    total_profit = trades_qs.aggregate(total=Sum("profit_amount"))["total"] or Decimal("0")
    profile.current_balance = profile.initial_balance + total_profit
    profile.save(update_fields=["current_balance"])


@receiver(post_save, sender=Trade)
def update_balance_after_trade_save(sender, instance: Trade, **kwargs) -> None:
    _recalculate_profile_balance(instance.user)


@receiver(post_delete, sender=Trade)
def update_balance_after_trade_delete(sender, instance: Trade, **kwargs) -> None:
    _recalculate_profile_balance(instance.user)
