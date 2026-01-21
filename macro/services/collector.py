import logging
import random
import time
from datetime import datetime
from typing import Iterable, List, Optional

from django.db import transaction
from django.utils import timezone

from macro.models import MacroAsset, MacroScore, MacroVariation, SourceChoices
from macro.services import config
from macro.services.network import fetch_html
from macro.services.parsers import PARSER_BY_SOURCE
from macro.services.utils import (
    align_measurement_time,
    extract_relevant_text,
    parse_variation_percent,
)


def _iter_assets() -> Iterable[MacroAsset]:
    return MacroAsset.objects.filter(active=True).order_by("name")


logger = logging.getLogger(__name__)


def execute_cycle(measurement_time: Optional[datetime] = None) -> None:
    """Executa coleta e persiste no banco."""
    measurement_time = measurement_time or align_measurement_time(
        timezone.now(), config.TARGET_INTERVAL_MINUTES
    )
    label = measurement_time.strftime("%Y-%m-%d %H:%M")
    logger.info("[macro] Iniciando ciclo para %s", label)

    assets = list(_iter_assets())
    variations: List[MacroVariation] = []
    scores: List[int] = []
    variation_sum = 0.0

    for asset in assets:
        outcome = fetch_html(asset)
        parser = PARSER_BY_SOURCE.get(asset.source_key)
        variation_text = parser(outcome.html) if parser and outcome.html else None
        market_phase = ""

        if asset.source_key == SourceChoices.TRADINGVIEW and variation_text:
            text = str(variation_text).strip()
            if text.startswith("EXT:"):
                market_phase = "ext"
                variation_text = text.replace("EXT:", "", 1).strip()
            elif text.startswith("REG:"):
                market_phase = "reg"
                variation_text = text.replace("REG:", "", 1).strip()

        variation_decimal = parse_variation_percent(variation_text)
        status = outcome.status
        if variation_text is None and status == "ok":
            status = "no_data"

        excerpt = extract_relevant_text(outcome.html or "")
        variations.append(
            MacroVariation(
                asset=asset,
                measurement_time=measurement_time,
                variation_text=variation_text,
                variation_decimal=variation_decimal,
                status=status,
                block_reason=outcome.block_reason or "",
                source_excerpt=excerpt,
                market_phase=market_phase,
            )
        )

        direction = 1 if asset.value_base >= 0 else -1
        adjusted_variation = (variation_decimal or 0.0) * direction
        variation_sum += adjusted_variation

        threshold = abs(asset.value_base)
        if variation_decimal is None:
            scores.append(0)
        elif adjusted_variation >= threshold:
            scores.append(1)
        elif adjusted_variation <= -threshold:
            scores.append(-1)
        else:
            scores.append(0)

        delay_min, delay_max = config.FETCH_DELAY_RANGE
        time.sleep(random.uniform(delay_min, delay_max))

    total_score = sum(scores)

    with transaction.atomic():
        MacroVariation.objects.bulk_create(variations, ignore_conflicts=True)
        MacroScore.objects.update_or_create(
            measurement_time=measurement_time,
            defaults={
                "total_score": total_score,
                "variation_sum": variation_sum,
            },
        )

    logger.info("[macro] Ciclo concluído (%s ativos) para %s", len(variations), label)
