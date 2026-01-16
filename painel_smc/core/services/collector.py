# Orquestra um ciclo completo de coleta para todos os ativos configurados
import random
import time
from datetime import datetime
from typing import List, Optional

from core import assets, config, data_sources, network, writers
from core.services import events
from core.models import VariationResult
from core.utils import extract_relevant_text, parse_variation_percent


def execute_cycle(measurement_time: Optional[datetime] = None) -> None:
    """Executa a coleta, persiste resultados e depuração."""
    run_label = (
        measurement_time.strftime("%Y-%m-%d %H:%M")
        if measurement_time
        else datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    print(f"[collector] Iniciando ciclo para janela {run_label}")

    asset_list = assets.load_assets()
    parser_cache = {}
    results: List[VariationResult] = []

    for asset in asset_list:
        print(f"[collector] (html) consultando {asset.source_key} para '{asset.name}' -> {asset.url}")
        fetch_outcome = network.fetch_html(asset)
        if not fetch_outcome.html:
            if asset.source_key == "tradingview":
                print(
                    f"[collector] tradingview sem HTML para '{asset.name}' "
                    f"(status={fetch_outcome.status}, reason={fetch_outcome.block_reason})"
                )
            results.append(
                VariationResult(
                    asset=asset,
                    variation_text=None,
                    variation_decimal=None,
                    status=fetch_outcome.status,
                    block_reason=fetch_outcome.block_reason,
                    source_excerpt="",
                )
            )
            continue

        parser = parser_cache.setdefault(asset.source_key, data_sources.get_parser(asset.source_key))
        variation_text = parser(fetch_outcome.html)
        market_phase = ""

        if asset.source_key == "tradingview" and variation_text:
            text = str(variation_text).strip()
            if text.startswith("EXT:"):
                market_phase = "ext"
                variation_text = text.replace("EXT:", "", 1).strip()
                print(f"[collector] tradingview pré/pós-mercado para '{asset.name}': {variation_text}")
            elif text.startswith("REG:"):
                market_phase = "reg"
                variation_text = text.replace("REG:", "", 1).strip()
                print(f"[collector] tradingview mercado regular para '{asset.name}': {variation_text}")
        elif asset.source_key == "tradingview" and variation_text is None:
            print(
                f"[collector] tradingview sem variação para '{asset.name}' "
                f"(status={fetch_outcome.status}, reason={fetch_outcome.block_reason})"
            )

        variation_decimal = parse_variation_percent(variation_text)
        status = fetch_outcome.status
        if variation_text is None:
            status = "no_data" if status == "ok" else status

        excerpt = extract_relevant_text(fetch_outcome.html)
        results.append(
            VariationResult(
                asset=asset,
                variation_text=variation_text,
                variation_decimal=variation_decimal,
                status=status,
                block_reason=fetch_outcome.block_reason,
                source_excerpt=excerpt,
                market_phase=market_phase,
            )
        )

        delay_min, delay_max = config.FETCH_DELAY_RANGE
        time.sleep(random.uniform(delay_min, delay_max))

    writers.write_variations(results, run_label)
    writers.write_metadata(results, run_label)
    writers.write_scores(results, run_label)
    writers.write_debug(results, run_label)
    events.signal_data_ready()
    print(f"[collector] Ciclo concluído e registros atualizados para {run_label}")

