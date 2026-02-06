from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

from accounts.models import Plan, Profile

logger = logging.getLogger(__name__)


DISCORD_API_BASE = "https://discord.com/api"


class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.period_seconds:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                sleep_for = self.period_seconds - (now - self._calls[0])
            if sleep_for > 0:
                time.sleep(sleep_for)


_discord_rate_limiter = RateLimiter(max_calls=10, period_seconds=1.0)


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


def _validate_bot_config(config: DiscordConfig) -> bool:
    if not config.bot_token:
        logger.error("[discord] DISCORD_BOT_TOKEN não configurado.")
        return False
    if not config.guild_id:
        logger.error("[discord] DISCORD_GUILD_ID não configurado.")
        return False
    return True


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

def _bot_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    while True:
        _discord_rate_limiter.wait()
        resp = requests.request(method, url, headers=_bot_headers(), timeout=20, **kwargs)
        if resp.status_code != 429:
            return resp
        try:
            payload = resp.json()
            retry_after = float(payload.get("retry_after", 1)) + 0.5
        except (ValueError, TypeError, json.JSONDecodeError):
            retry_after = 5
        logger.warning("[discord] Rate limit 429. Retry after: %s", retry_after)
        time.sleep(retry_after)


def add_role(discord_user_id: str, role_id: str) -> None:
    config = get_config()
    if not _validate_bot_config(config):
        return
    url = f"{DISCORD_API_BASE}/guilds/{config.guild_id}/members/{discord_user_id}/roles/{role_id}"
    resp = _bot_request("PUT", url)
    if resp.status_code in {401, 403}:
        logger.error(
            "[discord] Permissão negada ao adicionar role %s (status %s). "
            "Verifique Manage Roles e hierarquia do bot.",
            role_id,
            resp.status_code,
        )
    elif not resp.ok:
        logger.warning("[discord] Falha ao adicionar role %s: %s", role_id, resp.text)


def remove_role(discord_user_id: str, role_id: str) -> None:
    config = get_config()
    if not _validate_bot_config(config):
        return
    url = f"{DISCORD_API_BASE}/guilds/{config.guild_id}/members/{discord_user_id}/roles/{role_id}"
    resp = _bot_request("DELETE", url)
    if resp.status_code in {401, 403}:
        logger.error(
            "[discord] Permissão negada ao remover role %s (status %s). "
            "Verifique Manage Roles e hierarquia do bot.",
            role_id,
            resp.status_code,
        )
    elif not resp.ok and resp.status_code != 404:
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


def fetch_member_roles(discord_user_id: str) -> list[str] | None:
    config = get_config()
    if not _validate_bot_config(config):
        return None
    url = f"{DISCORD_API_BASE}/guilds/{config.guild_id}/members/{discord_user_id}"
    resp = _bot_request("GET", url)
    if resp.status_code == 404:
        logger.warning("[discord] Usuário não está no servidor: %s", discord_user_id)
        return None
    if resp.status_code in {401, 403}:
        logger.error(
            "[discord] Permissão negada ao buscar roles do usuário %s (status %s). "
            "Verifique Manage Roles, intents e hierarquia do bot.",
            discord_user_id,
            resp.status_code,
        )
        return None
    if not resp.ok:
        logger.warning("[discord] Falha ao buscar roles do usuário: %s", resp.text)
        return None
    data = resp.json()
    return data.get("roles", [])


def remove_all_roles(discord_user_id: str) -> None:
    config = get_config()
    current_roles = fetch_member_roles(discord_user_id)
    if current_roles is None:
        return
    for role_id in [config.role_basic_id, config.role_premium_id, config.role_premium_plus_id]:
        if role_id and role_id in current_roles:
            remove_role(discord_user_id, role_id)


def sync_profile_roles(profile: Profile) -> None:
    """Sincroniza roles de acordo com o plano."""
    if not profile.discord_user_id:
        logger.info("[discord] Perfil sem discord_user_id (user_id=%s).", profile.user_id)
        return

    current_roles = fetch_member_roles(profile.discord_user_id)
    if current_roles is None:
        logger.info(
            "[discord] Não foi possível obter roles do usuário %s (user_id=%s).",
            profile.discord_user_id,
            profile.user_id,
        )
        return

    active_plan = profile.active_plan()
    desired_role = desired_role_for_plan(active_plan)
    config = get_config()
    role_ids = [
        config.role_basic_id,
        config.role_premium_id,
        config.role_premium_plus_id,
    ]
    logger.info(
        "[discord] Sincronizando roles (user_id=%s, discord_id=%s, plan=%s, desired_role=%s).",
        profile.user_id,
        profile.discord_user_id,
        active_plan,
        desired_role or "none",
    )

    for role_id in role_ids:
        if not role_id:
            continue
        if desired_role == role_id:
            if role_id not in current_roles:
                add_role(profile.discord_user_id, role_id)
        else:
            if role_id in current_roles:
                remove_role(profile.discord_user_id, role_id)
