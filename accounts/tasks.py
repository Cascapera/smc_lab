"""Tasks Celery do app accounts."""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.utils import timezone

from .models import Plan, Profile

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(
    self,
    subject: str,
    body: str,
    from_email: str | None,
    to_email: str,
    html_body: str | None = None,
) -> None:
    """Envia o e-mail de recuperação fora do request.

    O SMTP da GoDaddy no caminho da requisição segurava um worker do gunicorn
    pelo tempo da conexão — e sem `EMAIL_TIMEOUT` isso não tinha teto. O corpo
    chega pronto porque o contexto do template carrega o objeto `User`, que não
    é serializável para a fila.
    """
    mensagem = EmailMultiAlternatives(subject, body, from_email, [to_email])
    if html_body:
        mensagem.attach_alternative(html_body, "text/html")
    try:
        mensagem.send()
    except Exception as exc:
        # Retentar importa: quem pediu a recuperação já viu "enviamos o e-mail"
        # e não tem como saber que o envio falhou.
        logger.error("[accounts] Falha ao enviar e-mail de recuperação: %s", exc, exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task
def clear_expired_sessions() -> None:
    """Remove sessões expiradas da tabela.

    Sem isto a `django_session` só cresce. Ela deixou de ser varrida a cada
    login (A7), mas continua sendo lida em toda requisição autenticada.
    """
    call_command("clearsessions")


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
            # Sem o e-mail: é dado pessoal e o log de INFO vai para arquivo e
            # para o journal do container. O ID identifica igual.
            logger.info("[accounts] Plano expirado: user_id=%s → Free", profile.user_id)
            try:
                from discord_integration.tasks import sync_user_roles

                sync_user_roles.delay(profile.user_id)
            except Exception as exc:
                # Era DEBUG, que não aparece em produção: o usuário ficava com a
                # role antiga no Discord e nada registrava o motivo.
                logger.warning(
                    "[accounts] Falha ao enfileirar sync_user_roles (user_id=%s): %s",
                    profile.user_id,
                    exc,
                )
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
