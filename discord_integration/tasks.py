import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from accounts.models import Profile

from .services import sync_profile_roles

logger = logging.getLogger(__name__)


# `soft_time_limit`: mesmo com o teto de 429 por requisição, uma sincronização
# pode encadear várias chamadas. O limite garante que a task devolve o worker.
@shared_task(soft_time_limit=120, time_limit=180)
def sync_user_roles(user_id: int) -> None:
    profile = Profile.objects.filter(user_id=user_id).first()
    if not profile or not profile.discord_user_id:
        return
    try:
        sync_profile_roles(profile)
    except Exception as exc:
        logger.error("[discord] Erro ao sincronizar usuário %s: %s", user_id, exc, exc_info=True)


@shared_task(soft_time_limit=600, time_limit=660)
def sync_all_discord_roles() -> None:
    profiles = Profile.objects.exclude(discord_user_id="").select_related("user")
    for profile in profiles:
        try:
            sync_profile_roles(profile)
        except SoftTimeLimitExceeded:
            # Interrompe a varredura inteira: insistir só empurra o estouro do
            # `time_limit`, que mata o worker no meio da tarefa.
            logger.error(
                "[discord] Sincronização diária interrompida por tempo limite (último perfil: %s).",
                profile.user_id,
            )
            raise
        except Exception as exc:
            logger.error(
                "[discord] Erro ao sincronizar perfil %s: %s",
                profile.user_id,
                exc,
                exc_info=True,
            )
