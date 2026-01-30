from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

from accounts.models import Plan, Profile

logger = logging.getLogger(__name__)


DISCORD_API_BASE = "https://discord.com/api"


@dataclass
class DiscordConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    bot_token: str
    guild_id: str
    role_basic_id: str
    role_premium_id: str
    role_premium_plus_id: str


def get_config() -> DiscordConfig:
    return DiscordConfig(
        client_id=settings.DISCORD_CLIENT_ID,
        client_secret=settings.DISCORD_CLIENT_SECRET,
        redirect_uri=settings.DISCORD_REDIRECT_URI,
        bot_token=settings.DISCORD_BOT_TOKEN,
        guild_id=settings.DISCORD_GUILD_ID,
        role_basic_id=settings.DISCORD_ROLE_BASIC_ID,
        role_premium_id=settings.DISCORD_ROLE_PREMIUM_ID,
        role_premium_plus_id=settings.DISCORD_ROLE_PREMIUM_PLUS_ID,
    )


def build_oauth_url(state: str) -> str:
    config = get_config()
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return f"{DISCORD_API_BASE}/oauth2/authorize?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    config = get_config()
    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"Erro Discord (token): {resp.text}")
    return resp.json()


def fetch_discord_user(access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{DISCORD_API_BASE}/users/@me", headers=headers, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"Erro Discord (user): {resp.text}")
    return resp.json()


def _bot_headers() -> dict[str, str]:
    config = get_config()
    return {"Authorization": f"Bot {config.bot_token}"}


def add_role(discord_user_id: str, role_id: str) -> None:
    config = get_config()
    url = f"{DISCORD_API_BASE}/guilds/{config.guild_id}/members/{discord_user_id}/roles/{role_id}"
    resp = requests.put(url, headers=_bot_headers(), timeout=20)
    if not resp.ok:
        logger.warning("[discord] Falha ao adicionar role %s: %s", role_id, resp.text)


def remove_role(discord_user_id: str, role_id: str) -> None:
    config = get_config()
    url = f"{DISCORD_API_BASE}/guilds/{config.guild_id}/members/{discord_user_id}/roles/{role_id}"
    resp = requests.delete(url, headers=_bot_headers(), timeout=20)
    if not resp.ok and resp.status_code != 404:
        logger.warning("[discord] Falha ao remover role %s: %s", role_id, resp.text)


def desired_role_for_plan(plan: str) -> str | None:
    config = get_config()
    if plan == Plan.BASIC:
        return config.role_basic_id
    if plan == Plan.PREMIUM:
        return config.role_premium_id
    if plan == Plan.PREMIUM_PLUS:
        return config.role_premium_plus_id
    return None


def remove_all_roles(discord_user_id: str) -> None:
    config = get_config()
    for role_id in [
        config.role_basic_id,
        config.role_premium_id,
        config.role_premium_plus_id,
    ]:
        if role_id:
            remove_role(discord_user_id, role_id)


def sync_profile_roles(profile: Profile) -> None:
    """Sincroniza roles de acordo com o plano."""
    if not profile.discord_user_id:
        return

    desired_role = desired_role_for_plan(profile.active_plan())
    config = get_config()
    role_ids = [
        config.role_basic_id,
        config.role_premium_id,
        config.role_premium_plus_id,
    ]

    for role_id in role_ids:
        if not role_id:
            continue
        if desired_role == role_id:
            add_role(profile.discord_user_id, role_id)
        else:
            remove_role(profile.discord_user_id, role_id)
