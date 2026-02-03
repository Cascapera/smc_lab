from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Profile, User

@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance: User, created: bool, **kwargs) -> None:
    profile, profile_created = Profile.objects.get_or_create(user=instance)
    if profile_created and profile.current_balance != profile.initial_balance:
        profile.current_balance = profile.initial_balance
        profile.save(update_fields=["current_balance"])


@receiver(user_logged_in)
def logout_other_sessions(sender, request, user: User, **kwargs) -> None:
    """Garante apenas uma sessão ativa por usuário."""
    if not request.session.session_key:
        request.session.save()
    current_key = request.session.session_key

    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in sessions:
        data = session.get_decoded()
        if data.get("_auth_user_id") == str(user.id) and session.session_key != current_key:
            session.delete()

