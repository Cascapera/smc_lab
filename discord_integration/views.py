from __future__ import annotations

import logging
import secrets

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
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
)
from .tasks import sync_user_roles

logger = logging.getLogger(__name__)


def _enfileirar_sync_apos_commit(user_id: int) -> None:
    """Enfileira a sincronização de roles depois que a transação fechar.

    Duas razões para o `on_commit`: com `ATOMIC_REQUESTS` ligado, um `.delay()`
    dentro da view faz o worker ler o estado anterior à gravação (foi o P6); e a
    exceção do broker aqui dentro estouraria no commit, virando 500 numa
    operação que já deu certo.
    """

    def _enfileirar() -> None:
        try:
            sync_user_roles.delay(user_id)
        except Exception as exc:
            logger.error(
                "[discord] Falha ao enfileirar sync_user_roles (user_id=%s): %s",
                user_id,
                exc,
                exc_info=True,
            )

    transaction.on_commit(_enfileirar)


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
        # `pop`: o state é de uso único. Mantido na sessão, um callback antigo
        # continuava válido enquanto a sessão durasse.
        expected_state = request.session.pop("discord_oauth_state", None)
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

        # Sem `id` não há vínculo: gravar string vazia com `discord_connected_at`
        # preenchido deixava o perfil "conectado" a ninguém, e ainda faria a
        # checagem de duplicidade abaixo casar com todas as contas sem Discord.
        discord_id = str(user_data.get("id") or "").strip()
        if not discord_id:
            logger.error("[discord] Resposta de /users/@me sem id (user_id=%s).", request.user.id)
            messages.error(request, "Erro ao conectar com o Discord. Tente novamente mais tarde.")
            return redirect(reverse("accounts:profile"))

        # Duas contas no mesmo Discord se anulam na sincronização diária: uma
        # adiciona a role, a outra remove. Recusamos aqui, onde dá para explicar
        # ao usuário, em vez de deixar a constraint estourar em 500.
        if Profile.objects.filter(discord_user_id=discord_id).exclude(pk=profile.pk).exists():
            logger.warning(
                "[discord] Conta Discord %s já vinculada a outro usuário (tentativa: user_id=%s).",
                discord_id,
                request.user.id,
            )
            messages.error(
                request,
                "Esta conta do Discord já está vinculada a outro usuário do SMC Lab. "
                "Desvincule-a na outra conta antes de conectar aqui.",
            )
            return redirect(reverse("accounts:profile"))

        profile.discord_user_id = discord_id
        username = user_data.get("username", "")
        discriminator = user_data.get("discriminator")
        if discriminator and discriminator != "0":
            username = f"{username}#{discriminator}"
        profile.discord_username = username
        profile.discord_connected_at = timezone.now()
        profile.save(update_fields=["discord_user_id", "discord_username", "discord_connected_at"])

        # Antes havia `sync_profile_roles()` síncrono AQUI e o `.delay()` logo
        # abaixo: o mesmo trabalho duas vezes, sendo que a versão síncrona fazia
        # até 4 requisições de 20s ao Discord segurando um worker do gunicorn.
        _enfileirar_sync_apos_commit(request.user.id)

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

        _enfileirar_sync_apos_commit(request.user.id)

        messages.success(request, "Discord desvinculado com sucesso.")
        return redirect(reverse("accounts:profile"))
