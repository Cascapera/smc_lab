"""
Retenção da tabela de variações macro.

Contexto: `MacroVariation` nunca teve limpeza. Em produção chegou a **1913 MB e
1.389.386 linhas — 87% do banco inteiro**, crescendo ~270 MB/mês. Cada backup
copiava tudo isso, então o dump ia para 2,2 GB e o disco caminhava para encher.

A causa do volume era o `source_excerpt` (HTML bruto, ~1,4 KB por linha),
gravado inclusive quando a coleta dava certo. O collector já não faz mais isso;
este módulo cuida do passivo e impede que volte a acumular.

O que NÃO é apagado: `MacroScore` (o histórico do painel, ~6 MB) e `MacroAsset`.
Só as variações individuais, que servem ao painel de curto prazo.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from macro.models import MacroVariation

logger = logging.getLogger(__name__)

# Lotes pequenos de propósito: apagar 1,3 milhão de linhas numa transação só
# trava a tabela e incha o WAL do Postgres. A coleta escreve a cada 5 min e não
# pode ficar esperando.
TAMANHO_LOTE_PADRAO = 5000

# Trava contra loop infinito caso algo dê errado na contagem.
MAX_LOTES = 10_000


def dias_de_retencao() -> int:
    return int(getattr(settings, "MACRO_VARIATION_RETENTION_DAYS", 90))


def purgar_variacoes_antigas(
    dias: int | None = None,
    tamanho_lote: int = TAMANHO_LOTE_PADRAO,
    dry_run: bool = False,
) -> dict:
    """
    Remove variações mais antigas que `dias`, em lotes.

    Retorna um dict com o que foi encontrado e o que foi removido. Com
    `dry_run=True` apenas conta, sem apagar nada.
    """
    dias = dias_de_retencao() if dias is None else int(dias)
    if dias < 1:
        raise ValueError("A retenção precisa ser de pelo menos 1 dia.")

    corte = timezone.now() - timedelta(days=dias)
    antigas = MacroVariation.objects.filter(measurement_time__lt=corte)
    total_encontrado = antigas.count()

    resultado = {
        "dias": dias,
        "corte": corte.isoformat(),
        "encontradas": total_encontrado,
        "removidas": 0,
        "lotes": 0,
        "dry_run": dry_run,
    }

    if dry_run or total_encontrado == 0:
        logger.info(
            "[macro] Retenção (%s): %d variações anteriores a %s",
            "simulação" if dry_run else "nada a remover",
            total_encontrado,
            corte.isoformat(),
        )
        return resultado

    removidas = 0
    for lote in range(MAX_LOTES):
        ids = list(
            MacroVariation.objects.filter(measurement_time__lt=corte).values_list("id", flat=True)[
                :tamanho_lote
            ]
        )
        if not ids:
            break
        MacroVariation.objects.filter(id__in=ids).delete()
        removidas += len(ids)
        resultado["lotes"] = lote + 1
    else:
        logger.error(
            "[macro] Retenção parou no limite de %d lotes; rode novamente.",
            MAX_LOTES,
        )

    resultado["removidas"] = removidas
    logger.info(
        "[macro] Retenção concluída: %d variações removidas em %d lote(s), corte em %s",
        removidas,
        resultado["lotes"],
        corte.isoformat(),
    )
    return resultado
