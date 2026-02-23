from __future__ import annotations

import logging
import secrets

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from accounts.models import Profile

from .services import (
    build_oauth_url,
    exchange_code_for_token,
    fetch_discord_user,
    remove_all_roles,
    sync_profile_roles,
)
from .tasks import sync_user_roles

logger = logging.getLogger(__name__)


class DiscordLoginView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.session.session_key:
            request.session.save()

        try:
            from django.conf import settings

            if (
                not settings.DISCORD_CLIENT_ID
                or not settings.DISCORD_CLIENT_SECRET
                or not settings.DISCORD_REDIRECT_URI
            ):
                messages.error(request, "Discord não configurado. Tente novamente mais tarde.")
                return redirect(reverse("accounts:profile"))

            state = secrets.token_urlsafe(16)
            request.session["discord_oauth_state"] = state
            oauth_url = build_oauth_url(state)
        except Exception as exc:
            logger.exception("[discord] Erro ao iniciar OAuth: %s", exc)
            messages.error(request, "Discord não configurado. Tente novamente mais tarde.")
            return redirect(reverse("accounts:profile"))

        return redirect(oauth_url)


class DiscordCallbackView(LoginRequiredMixin, View):
    def get(self, request):
        state = request.GET.get("state")
        code = request.GET.get("code")
        expected_state = request.session.get("discord_oauth_state")
        if not state or state != expected_state:
            messages.error(request, "Falha na autenticação do Discord.")
            return redirect(reverse("accounts:profile"))

        if not code:
            messages.error(request, "Autorização do Discord não recebida.")
            return redirect(reverse("accounts:profile"))

        try:
            token_data = exchange_code_for_token(code)
            user_data = fetch_discord_user(token_data.get("access_token", ""))
        except Exception as exc:
            logger.exception(
                "[discord] Erro ao conectar no callback (user_id=%s): %s", request.user.id, exc
            )
            messages.error(request, "Erro ao conectar com o Discord. Tente novamente mais tarde.")
            return redirect(reverse("accounts:profile"))

        profile = Profile.objects.filter(user=request.user).first()
        if not profile:
            messages.error(request, "Perfil não encontrado.")
            return redirect(reverse("accounts:profile"))

        profile.discord_user_id = str(user_data.get("id", ""))
        username = user_data.get("username", "")
        discriminator = user_data.get("discriminator")
        if discriminator and discriminator != "0":
            username = f"{username}#{discriminator}"
        profile.discord_username = username
        profile.discord_connected_at = timezone.now()
        profile.save(update_fields=["discord_user_id", "discord_username", "discord_connected_at"])

        try:
            sync_profile_roles(profile)
        except Exception as exc:
            logger.error(
                "[discord] Falha ao sincronizar roles no callback (user_id=%s): %s",
                request.user.id,
                exc,
                exc_info=True,
            )

        try:
            sync_user_roles.delay(request.user.id)
        except Exception as exc:
            logger.error(
                "[discord] Falha ao enfileirar sync_user_roles (user_id=%s): %s",
                request.user.id,
                exc,
                exc_info=True,
            )

        messages.success(request, "Discord conectado com sucesso!")
        return redirect(reverse("accounts:profile"))


class DiscordUnlinkView(LoginRequiredMixin, View):
    def post(self, request):
        profile = Profile.objects.filter(user=request.user).first()
        if not profile or not profile.discord_user_id:
            messages.warning(request, "Nenhuma conta Discord vinculada.")
            return redirect(reverse("accounts:profile"))

        discord_id = profile.discord_user_id
        try:
            remove_all_roles(discord_id)
        except Exception as exc:
            logger.error(
                "[discord] Falha ao remover roles no unlink (discord_id=%s): %s",
                discord_id,
                exc,
                exc_info=True,
            )

        profile.discord_user_id = ""
        profile.discord_username = ""
        profile.discord_connected_at = None
        profile.save(update_fields=["discord_user_id", "discord_username", "discord_connected_at"])

        try:
            sync_user_roles.delay(request.user.id)
        except Exception as exc:
            logger.error(
                "[discord] Falha ao enfileirar sync_user_roles no unlink (user_id=%s): %s",
                request.user.id,
                exc,
                exc_info=True,
            )

        messages.success(request, "Discord desvinculado com sucesso.")
        return redirect(reverse("accounts:profile"))
