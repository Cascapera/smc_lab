"""Tasks Celery do app accounts."""

import logging

from celery import shared_task
from django.utils import timezone

from .models import Plan, Profile

logger = logging.getLogger(__name__)


@shared_task
def downgrade_expired_plans() -> int:
    """
    Atualiza perfis com plano expirado para Free no banco.
    O active_plan() já retorna FREE quando expirado, mas o campo plan
    permanecia antigo — o admin e relatórios mostravam dados incorretos.
    """
    now = timezone.now()
    expired = Profile.objects.filter(
        plan_expires_at__lt=now,
        plan_expires_at__isnull=False,
    ).exclude(plan=Plan.FREE)

    count = 0
    for profile in expired:
        try:
            profile.plan = Plan.FREE
            profile.plan_expires_at = None
            profile.save(update_fields=["plan", "plan_expires_at"])
            count += 1
            logger.info(
                "[accounts] Plano expirado: %s (ID %d) → Free",
                profile.user.email,
                profile.user_id,
            )
            try:
                from discord_integration.tasks import sync_user_roles

                sync_user_roles.delay(profile.user_id)
            except Exception as exc:
                logger.debug("[accounts] sync_user_roles não disponível: %s", exc)
        except Exception as exc:
            logger.error(
                "[accounts] Erro ao fazer downgrade de %s: %s",
                profile.user_id,
                exc,
                exc_info=True,
            )

    if count:
        logger.info("[accounts] %d perfil(is) com plano expirado atualizado(s) para Free.", count)
    return count
