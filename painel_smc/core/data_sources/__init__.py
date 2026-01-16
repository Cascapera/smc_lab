# Encaminha o HTML para o parser correto com base na origem do ativo
from typing import Callable, Dict, Optional

from .investing import parse_variation as parse_investing
from .tradingview import parse_variation as parse_tradingview

ParserFn = Callable[[str], Optional[str]]

PARSERS: Dict[str, ParserFn] = {
    "investing": parse_investing,
    "tradingview": parse_tradingview,
}


def get_parser(source_key: str) -> ParserFn:
    """Obtém o parser adequado; padrão é Investing."""
    return PARSERS.get(source_key, parse_investing)

