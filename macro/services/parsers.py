from typing import Callable, Optional

from bs4 import BeautifulSoup


def parse_investing_variation(html: str) -> Optional[str]:
    """Localiza a variação percentual no HTML do Investing."""
    soup = BeautifulSoup(html, "html.parser")

    def _has_premarket_class(classes: object) -> bool:
        if not classes:
            return False
        class_list = classes if isinstance(classes, list) else str(classes).split()
        return "notranslate" in class_list and "order-4" in class_list

    candidate = next(
        (
            span
            for span in soup.find_all("span", class_=_has_premarket_class)
            if "%" in span.get_text()
        ),
        None,
    )

    if candidate is None:
        candidate = soup.find("span", {"data-test": "instrument-price-change-percent"})
        if candidate is None:
            return None

    text = candidate.get_text(separator="", strip=True)
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    text = text.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not text.endswith("%"):
        text = f"{text}%"
    return text


def _normalize_tradingview(text: str) -> str:
    cleaned = (
        text.replace("\u2212", "-")
        .replace("\u00a0", "")
        .strip()
    )
    if not cleaned.endswith("%"):
        cleaned = f"{cleaned}%"
    return cleaned


def parse_tradingview_variation(html: str) -> Optional[str]:
    """Prioriza pré/pós-mercado; se não encontrar, usa variação regular."""
    soup = BeautifulSoup(html, "html.parser")

    ext_span = soup.find("span", class_="js-symbol-ext-hrs-change-pt")
    if ext_span and ext_span.get_text(strip=True):
        return f"EXT:{_normalize_tradingview(ext_span.get_text(strip=True))}"

    reg_span = soup.find("span", class_="js-symbol-change-pt")
    if reg_span and reg_span.get_text(strip=True):
        return f"REG:{_normalize_tradingview(reg_span.get_text(strip=True))}"

    return None


ParserFunc = Callable[[str], Optional[str]]

PARSER_BY_SOURCE = {
    "investing": parse_investing_variation,
    "tradingview": parse_tradingview_variation,
}
