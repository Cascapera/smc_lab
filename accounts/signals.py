from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, User

@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance: User, created: bool, **kwargs) -> None:
    profile, profile_created = Profile.objects.get_or_create(user=instance)
    if profile_created and profile.current_balance != profile.initial_balance:
        profile.current_balance = profile.initial_balance
        profile.save(update_fields=["current_balance"])
