# Modelos de dados principais utilizados em todo o projeto
from dataclasses import dataclass
from typing import Optional


# fmt: off
@dataclass
class Asset:
    """Representa um ativo monitorado, incluindo a origem de dados."""
    name: str
    value_base: float
    url: str
    source_key: str
    ticker: str = ""
    category: str = ""


@dataclass
class VariationResult:
    """Concentra o resultado da coleta de um ativo."""
    asset: Asset
    variation_text: Optional[str]
    variation_decimal: Optional[float]
    status: str
    block_reason: Optional[str] = None
    source_excerpt: str = ""
    market_phase: str = ""
# fmt: on

