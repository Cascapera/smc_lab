# Carrega e normaliza os ativos a partir da planilha de referência
from typing import List
from urllib.parse import urlparse

import pandas as pd

from core import config
from core.models import Asset


def _ensure_reference_file() -> None:
    """Garante que a planilha esteja na pasta de dados (migra se necessário)."""
    config.DATA_SOURCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    legacy_path = config.BASE_DIR / config.DATA_SOURCE_PATH.name
    if config.DATA_SOURCE_PATH.exists():
        return
    if legacy_path.exists():
        legacy_path.replace(config.DATA_SOURCE_PATH)


def _find_category_column(df: pd.DataFrame):
    """Retorna o nome da coluna categoria/category (case-insensitive), se existir."""
    for col in df.columns:
        if col.lower() in {"categoria", "category"}:
            return col
    return None


def load_assets() -> List[Asset]:
    """Lê a planilha, valida colunas e devolve lista de objetos Asset."""
    _ensure_reference_file()
    df = pd.read_excel(config.DATA_SOURCE_PATH)
    category_col = _find_category_column(df)

    required_base = {"Ativo", "ValorBase", "URL"}
    missing = required_base.difference(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes na planilha: {missing}")

    assets: List[Asset] = []
    for _, row in df.iterrows():
        name = str(row["Ativo"]).strip()
        value_base = float(row["ValorBase"])
        raw_url = row["URL"]
        url = "" if pd.isna(raw_url) else str(raw_url).strip()

        category = ""
        if category_col:
            raw_cat = row[category_col]
            if pd.notna(raw_cat):
                category = str(raw_cat).strip()

        if not url:
            raise ValueError(f"URL em branco para ativo '{name}'. Preencha com link do Investing.")

        netloc = urlparse(url).netloc.lower()
        if "investing.com" in netloc:
            source_key = "investing"
        elif "tradingview.com" in netloc:
            source_key = "tradingview"
        else:
            raise ValueError(
                f"Ativo '{name}' está apontando para domínio não suportado ({netloc}). "
                "Use apenas URLs do Investing ou TradingView."
            )

        assets.append(
            Asset(
                name=name,
                value_base=value_base,
                url=url,
                source_key=source_key,
                ticker="",
                category=category,
            )
        )
    return assets

