"""Funções auxiliares para extrair valores pontuais usados nos painéis."""

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from core.utils import parse_variation_percent


def load_latest_variation(
    asset_name: str,
    variations_path: Path,
    *,
    since: datetime | None = None,
) -> Tuple[str, Optional[str], Optional[float]]:
    """Retorna (label_coluna, texto_percentual, valor_decimal) da última medição do ativo."""
    if not variations_path.exists():
        raise FileNotFoundError(f"Arquivo '{variations_path}' não encontrado.")

    df = pd.read_csv(variations_path)
    if "Ativo" not in df.columns:
        raise ValueError("Coluna 'Ativo' ausente em historico_variacoes.csv")

    if asset_name not in df["Ativo"].values:
        raise ValueError(f"Ativo '{asset_name}' não encontrado em historico_variacoes.csv")

    candidate_columns = [col for col in df.columns if col != "Ativo"]

    if since is not None:
        timestamps = pd.to_datetime(candidate_columns, errors="coerce")
        candidate_columns = [col for col, ts in zip(candidate_columns, timestamps) if ts is not pd.NaT and ts >= since]
        if not candidate_columns:
            raise ValueError("Nenhuma variação recente disponível após o início da sessão.")

    last_column = candidate_columns[-1]
    raw_value = df.loc[df["Ativo"] == asset_name, last_column].iloc[0]
    text_value = None if pd.isna(raw_value) else str(raw_value).strip() or None
    decimal_value = parse_variation_percent(text_value)

    return last_column, text_value, decimal_value

