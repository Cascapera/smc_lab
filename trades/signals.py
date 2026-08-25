from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_delete, post_save, pre_save
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


def _apagar_arquivo(campo) -> None:
    """Remove o arquivo do disco sem tocar no banco."""
    if not campo:
        return
    try:
        campo.delete(save=False)
    except Exception:  # noqa: BLE001 - falha ao apagar nao pode derrubar o request
        pass


@receiver(pre_save, sender=Trade)
def remover_captura_substituida(sender, instance: Trade, **kwargs) -> None:
    """
    Apaga a captura anterior quando o usuário envia outra.

    Sem isto, cada troca de imagem deixava um arquivo órfão no volume `media`,
    sem nada que o limpasse depois.
    """
    if not instance.pk:
        return
    try:
        anterior = Trade.objects.get(pk=instance.pk)
    except Trade.DoesNotExist:
        return
    if anterior.screenshot and anterior.screenshot.name != (instance.screenshot.name or ""):
        _apagar_arquivo(anterior.screenshot)


@receiver(post_delete, sender=Trade)
def remover_captura_do_trade_apagado(sender, instance: Trade, **kwargs) -> None:
    """Apagar o trade deixava a imagem no disco para sempre."""
    _apagar_arquivo(instance.screenshot)
