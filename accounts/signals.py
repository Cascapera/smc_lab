from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, User


@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance: User, created: bool, **kwargs) -> None:
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def logout_other_sessions(sender, request, user: User, **kwargs) -> None:
    """Garante apenas uma sessão ativa por usuário.

    Antes isto varria `django_session` inteira e chamava `get_decoded()` linha a
    linha — descriptografia por sessão, a cada login, dentro da transação da
    requisição. Com 20 mil sessões eram 20 mil decodificações para achar, no
    máximo, uma. O login degradava na exata proporção do tráfego.

    Agora o perfil guarda a sessão vigente e apagamos só ela.

    Limite conhecido: sessões abertas antes deste deploy não estão registradas
    em lugar nenhum, então o próximo login do usuário não as derruba. Elas
    expiram pelo `clearsessions` (`accounts.tasks.clear_expired_sessions`).
    """
    if not request.session.session_key:
        request.session.save()
    current_key = request.session.session_key

    profile = Profile.objects.filter(user=user).first()
    if profile is None:
        return

    sessao_anterior = profile.current_session_key
    if sessao_anterior and sessao_anterior != current_key:
        Session.objects.filter(session_key=sessao_anterior).delete()

    if sessao_anterior != current_key:
        profile.current_session_key = current_key or ""
        profile.save(update_fields=["current_session_key"])
