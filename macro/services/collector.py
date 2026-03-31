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
    is_market_closed,
    parse_variation_percent,
)
from trader_portal.observability import Timer, log_event


def _iter_assets() -> Iterable[MacroAsset]:
    return MacroAsset.objects.filter(active=True).order_by("name")


logger = logging.getLogger(__name__)


def _compute_score_and_adjusted_variation(asset, variation_decimal: Optional[float]) -> tuple:
    """
    Calcula score (-1, 0 ou 1) e variação ajustada para um ativo.
    Retorna (score, adjusted_variation).
    """
    direction = 1 if asset.value_base >= 0 else -1
    adjusted_variation = (variation_decimal or 0.0) * direction
    threshold = abs(asset.value_base)
    if variation_decimal is None:
        score = 0
    elif adjusted_variation >= threshold:
        score = 1
    elif adjusted_variation <= -threshold:
        score = -1
    else:
        score = 0
    return score, adjusted_variation


def _tradingview_window_open(measurement_time: datetime) -> bool:
    """Retorna True se a janela de coleta do TradingView estiver aberta (BRT)."""
    local_time = timezone.localtime(measurement_time)
    if local_time.weekday() >= 5:
        return False
    if local_time.hour < 6 or local_time.hour >= 21:
        return False
    return True


def execute_cycle(measurement_time: Optional[datetime] = None) -> None:
    """Executa coleta e persiste no banco."""
    try:
        measurement_time = measurement_time or align_measurement_time(
            timezone.now(), config.TARGET_INTERVAL_MINUTES
        )
        if is_market_closed(measurement_time):
            return
    except Exception as exc:
        logger.error("[macro] Erro ao inicializar ciclo: %s", exc, exc_info=True)
        raise

    label = measurement_time.strftime("%Y-%m-%d %H:%M")

    assets = list(_iter_assets())
    last_variations = {}
    if assets:
        last_qs = (
            MacroVariation.objects.filter(asset__in=assets, variation_decimal__isnull=False)
            .order_by("asset_id", "-measurement_time")
            .values(
                "asset_id",
                "variation_decimal",
                "variation_text",
                "market_phase",
            )
        )
        for row in last_qs:
            if row["asset_id"] not in last_variations:
                last_variations[row["asset_id"]] = row
    variations: List[MacroVariation] = []
    scores: List[int] = []
    variation_sum = 0.0
    total_bytes = 0

    for asset in assets:
        try:
            if asset.source_key == SourceChoices.TRADINGVIEW and not _tradingview_window_open(
                measurement_time
            ):
                fallback = last_variations.get(asset.id)
                variation_decimal = fallback["variation_decimal"] if fallback else None
                variation_text = fallback["variation_text"] if fallback else None
                market_phase = fallback["market_phase"] if fallback else ""

                variations.append(
                    MacroVariation(
                        asset=asset,
                        measurement_time=measurement_time,
                        variation_text=variation_text,
                        variation_decimal=variation_decimal,
                        status="fallback" if fallback else "no_data",
                        block_reason="tradingview_off_hours",
                        source_excerpt="",
                        market_phase=market_phase or "",
                        payload_bytes=None,
                    )
                )

                score, adjusted_variation = _compute_score_and_adjusted_variation(
                    asset, variation_decimal
                )
                variation_sum += adjusted_variation
                scores.append(score)
                continue

            log_event(
                logger,
                event="macro_fetch_started",
                message="External fetch",
                asset=asset.name,
                source=asset.source_key,
                status="started",
            )
            fetch_timer = Timer()
            try:
                with fetch_timer:
                    outcome = fetch_html(asset)
            except Exception as fetch_exc:
                log_event(
                    logger,
                    event="macro_fetch_failed",
                    message="fetch_html raised",
                    asset=asset.name,
                    source=asset.source_key,
                    status="error",
                    step="fetch_html",
                    elapsed_ms=fetch_timer.duration_ms,
                    error=str(fetch_exc),
                    exception_type=type(fetch_exc).__name__,
                    level=logging.ERROR,
                )
                raise
            log_event(
                logger,
                event="macro_fetch_completed",
                message="Fetch returned",
                asset=asset.name,
                source=asset.source_key,
                status="success" if outcome.status == "ok" else "error",
                elapsed_ms=fetch_timer.duration_ms,
                fetch_status=outcome.status,
                error=outcome.block_reason,
            )
            payload_bytes = len(outcome.html.encode("utf-8")) if outcome.html else 0
            total_bytes += payload_bytes
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

            if variation_decimal is None:
                fallback = last_variations.get(asset.id)
                if fallback:
                    variation_decimal = fallback["variation_decimal"]
                    if not variation_text:
                        variation_text = fallback["variation_text"]
                    if not market_phase:
                        market_phase = fallback["market_phase"] or ""
                    status = "fallback"
                    if not outcome.block_reason:
                        outcome.block_reason = "last_known"

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
                    payload_bytes=payload_bytes or None,
                )
            )

            score, adjusted_variation = _compute_score_and_adjusted_variation(
                asset, variation_decimal
            )
            variation_sum += adjusted_variation
            scores.append(score)

            delay_min, delay_max = config.FETCH_DELAY_RANGE
            time.sleep(random.uniform(delay_min, delay_max))
        except Exception as exc:
            log_event(
                logger,
                event="macro_fetch_failed",
                message="Asset processing failed",
                asset=asset.name,
                source=asset.source_key,
                status="error",
                step="asset_processing",
                error=str(exc),
                exception_type=type(exc).__name__,
                level=logging.ERROR,
            )
            logger.error(
                "[macro] Erro ao coletar ativo %s (ID: %d): %s",
                asset.name,
                asset.id,
                str(exc),
                exc_info=True,
            )
            # Continua para o próximo ativo mesmo se este falhar
            scores.append(0)
            continue

    total_score = sum(scores)

    try:
        with transaction.atomic():
            MacroVariation.objects.bulk_create(variations, ignore_conflicts=True)
            MacroScore.objects.update_or_create(
                measurement_time=measurement_time,
                defaults={
                    "total_score": total_score,
                    "variation_sum": variation_sum,
                },
            )
    except Exception as exc:
        logger.error(
            "[macro] Erro ao persistir dados no banco para %s: %s",
            label,
            str(exc),
            exc_info=True,
        )
        raise
