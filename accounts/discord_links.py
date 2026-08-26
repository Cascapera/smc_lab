"""
Resolução de contas que apontam para o mesmo Discord.

`discord_user_id` nunca teve unicidade. Duas contas podendo vincular o mesmo
Discord fazem a sincronização diária das 04:00 se anular: ela processa os perfis
por ordem de pk, então a conta free remove a role que a conta paga acabou de
adicionar. O pagante fica sem acesso, todo dia.

Antes de criar a constraint é preciso desempatar o que já está no banco. Regra
combinada com o Guilherme: **fica com o pagante; havendo empate, com o vínculo
mais recente**. Usamos `PLAN_RANK` para o critério de "pagante" — assim, se as
duas contas pagam, prevalece o plano maior, que é a mesma regra de precedência
já adotada nos pagamentos (P3).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from datetime import timezone as dt_timezone

from django.utils import timezone

from .models import PLAN_RANK, Plan

logger = logging.getLogger(__name__)

# Sentinela para perfis sem `discord_connected_at` (vínculos antigos, gravados
# antes do campo existir): perdem de qualquer vínculo datado.
_SEM_DATA = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)

_CAMPOS_DISCORD = ["discord_user_id", "discord_username", "discord_connected_at"]


def _plano_vigente(profile, agora: datetime) -> str:
    """Espelha `Profile.active_plan()` sem depender do método.

    A função roda dentro de uma migração de dados, onde o model é histórico e
    não tem métodos — por isso a regra é recalculada a partir dos campos.
    """
    if profile.plan_expires_at and profile.plan_expires_at < agora:
        return Plan.FREE
    return profile.plan


def _criterio_de_desempate(profile, agora: datetime) -> tuple[int, datetime, int]:
    return (
        PLAN_RANK.get(_plano_vigente(profile, agora), -1),
        profile.discord_connected_at or _SEM_DATA,
        profile.pk,
    )


def resolve_duplicate_discord_links(profile_model, agora: datetime | None = None) -> list:
    """Deixa no máximo um perfil por `discord_user_id`.

    Os perdedores têm os campos de Discord limpos (ficam como conta sem Discord
    vinculado, podendo vincular de novo). Retorna a lista de perfis limpos.
    """
    agora = agora or timezone.now()

    por_discord_id: dict[str, list] = defaultdict(list)
    for profile in profile_model.objects.exclude(discord_user_id=""):
        por_discord_id[profile.discord_user_id].append(profile)

    limpos = []
    for discord_id, perfis in por_discord_id.items():
        if len(perfis) < 2:
            continue

        vencedor = max(perfis, key=lambda p: _criterio_de_desempate(p, agora))
        for perfil in perfis:
            if perfil.pk == vencedor.pk:
                continue
            perfil.discord_user_id = ""
            perfil.discord_username = ""
            perfil.discord_connected_at = None
            perfil.save(update_fields=_CAMPOS_DISCORD)
            limpos.append(perfil)

        logger.warning(
            "[discord] discord_user_id %s estava em %d contas. "
            "Mantido no perfil %s; desvinculado de %s.",
            discord_id,
            len(perfis),
            vencedor.pk,
            [p.pk for p in perfis if p.pk != vencedor.pk],
        )

    return limpos
