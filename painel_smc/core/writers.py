# Responsável por persistir resultados (CSV principais, metadata e debug)
from pathlib import Path
from typing import List

import pandas as pd

from core import config
from core.models import VariationResult


def _prepare_path(path: Path) -> None:
    """Garante a existência do diretório e migra arquivos antigos para a nova pasta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path = config.BASE_DIR / path.name
    if not path.exists() and legacy_path.exists():
        legacy_path.replace(path)


def write_variations(results: List[VariationResult], column_label: str) -> None:
    """Atualiza o CSV de variações, criando uma coluna por medição."""
    assets = [result.asset.name for result in results]
    value_map = {result.asset.name: result.variation_text for result in results}

    _prepare_path(config.VARIATIONS_PATH)
    if config.VARIATIONS_PATH.exists():
        df = pd.read_csv(config.VARIATIONS_PATH)
    else:
        df = pd.DataFrame({"Ativo": assets})

    if "Ativo" not in df.columns:
        df.insert(0, "Ativo", assets)

    new_values = [value_map.get(asset) for asset in df["Ativo"]]
    df[column_label] = new_values
    df.to_csv(config.VARIATIONS_PATH, index=False)


def write_metadata(results: List[VariationResult], run_label: str) -> None:
    """Atualiza o CSV de metadata detalhada."""
    rows = [
        {
            "Ativo": result.asset.name,
            "timestamp": run_label,
            "status": result.status,
            "variation_pct": result.variation_text,
            "variation_decimal": result.variation_decimal,
            "html_variation_pct": result.variation_text,
            "block_reason": result.block_reason,
        }
        for result in results
    ]
    metadata_df = pd.DataFrame(rows)

    _prepare_path(config.METADATA_PATH)
    if config.METADATA_PATH.exists():
        existing = pd.read_csv(config.METADATA_PATH)
        combined = pd.concat([existing, metadata_df], ignore_index=True)
    else:
        combined = metadata_df

    combined.to_csv(config.METADATA_PATH, index=False)


def write_debug(results: List[VariationResult], run_label: str) -> None:
    """Grava o arquivo de depuração com trechos relevantes do HTML."""
    lines = [
        f"=== Ciclo armazenado para {run_label} ===",
        "",
    ]
    for result in results:
        lines.extend(
            [
                "=" * 90,
                f"Ativo: {result.asset.name}",
                f"URL: {result.asset.url}",
                f"Janela alvo: {run_label}",
                f"Status: {result.status} | Variação: {result.variation_text} | Motivo bloqueio: {result.block_reason}",
                "Texto limpo:",
                result.source_excerpt,
                "",
            ]
        )

    _prepare_path(config.DEBUG_PATH)
    config.DEBUG_PATH.write_text("\n".join(lines), encoding="utf-8")


# Atualiza a tabela de scores, invertendo sinais quando ValorBase for negativo
def write_scores(results: List[VariationResult], column_label: str) -> None:
    """Atualiza (ou cria) a tabela de scores (-1/0/1) respeitando ValorBase negativo."""
    asset_names = [result.asset.name for result in results]
    scores = []
    variation_sum = 0.0
    for result in results:
        direction = 1 if result.asset.value_base >= 0 else -1
        variation_decimal = result.variation_decimal or 0.0
        adjusted_variation = variation_decimal * direction
        variation_sum += adjusted_variation

        threshold = abs(result.asset.value_base)
        if result.variation_decimal is None:
            scores.append(0)
            continue

        if adjusted_variation >= threshold:
            scores.append(1)
        elif adjusted_variation <= -threshold:
            scores.append(-1)
        else:
            scores.append(0)

    total_score = sum(scores)

    _prepare_path(config.SCORES_PATH)
    expected_rows = asset_names + ["Soma", "Soma Acumulada"]
    if config.SCORES_PATH.exists():
        df = pd.read_csv(config.SCORES_PATH)
        if list(df["Ativo"]) != expected_rows:
            df = pd.DataFrame({"Ativo": expected_rows})
    else:
        df = pd.DataFrame({"Ativo": expected_rows})

    new_column = scores + [total_score, f"{variation_sum:+.6f}"]
    df[column_label] = new_column
    df.to_csv(config.SCORES_PATH, index=False)

