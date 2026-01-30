import logging

from celery import shared_task

from accounts.models import Profile
from .services import sync_profile_roles

logger = logging.getLogger(__name__)


@shared_task
def sync_user_roles(user_id: int) -> None:
    profile = Profile.objects.filter(user_id=user_id).first()
    if not profile or not profile.discord_user_id:
        return
    try:
        sync_profile_roles(profile)
    except Exception as exc:
        logger.error("[discord] Erro ao sincronizar usuário %s: %s", user_id, exc, exc_info=True)


@shared_task
def sync_all_discord_roles() -> None:
    profiles = Profile.objects.exclude(discord_user_id="")
    for profile in profiles:
        try:
            sync_profile_roles(profile)
        except Exception as exc:
            logger.error(
                "[discord] Erro ao sincronizar perfil %s: %s",
                profile.user_id,
                exc,
                exc_info=True,
            )
