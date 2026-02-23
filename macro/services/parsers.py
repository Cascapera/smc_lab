import json
from typing import Any, Callable, Optional

from bs4 import BeautifulSoup


def _normalize_percent_text(text: str) -> Optional[str]:
    cleaned = text.replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    if not cleaned:
        return None
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1]
    if not cleaned.endswith("%"):
        cleaned = f"{cleaned}%"
    return cleaned


def _format_percent_number(value: float) -> str:
    abs_value = abs(value)
    if abs_value < 0.2:
        value *= 100.0
    return f"{value:.2f}%"


def _extract_percent_from_json(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_lower = str(key).lower()
            if isinstance(value, (dict, list)):
                candidate = _extract_percent_from_json(value)
                if candidate:
                    return candidate
                continue
            if "percent" in key_lower or "pct" in key_lower:
                if isinstance(value, (int, float)):
                    return _format_percent_number(float(value))
                if isinstance(value, str):
                    normalized = _normalize_percent_text(value)
                    if normalized:
                        return normalized
        return None
    if isinstance(payload, list):
        for item in payload:
            candidate = _extract_percent_from_json(item)
            if candidate:
                return candidate
    return None


def parse_investing_variation(html: str) -> Optional[str]:
    """Localiza a variação percentual no HTML do Investing."""
    if not html:
        return None

    if html.lstrip().startswith(("{", "[")):
        try:
            payload = json.loads(html)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            return _extract_percent_from_json(payload)

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
    return _normalize_percent_text(text)


def _normalize_tradingview(text: str) -> str:
    cleaned = text.replace("\u2212", "-").replace("\u00a0", "").strip()
    if not cleaned.endswith("%"):
        cleaned = f"{cleaned}%"
    return cleaned


def _extract_tradingview_percent_json(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_lower = str(key).lower()
            if isinstance(value, (dict, list)):
                candidate = _extract_tradingview_percent_json(value)
                if candidate:
                    return candidate
                continue
            if "change" in key_lower and "percent" in key_lower:
                if isinstance(value, (int, float)):
                    return _normalize_tradingview(f"{value}")
                if isinstance(value, str):
                    normalized = _normalize_percent_text(value)
                    if normalized:
                        return normalized
        return None
    if isinstance(payload, list):
        for item in payload:
            candidate = _extract_tradingview_percent_json(item)
            if candidate:
                return candidate
    return None


def parse_tradingview_variation(html: str) -> Optional[str]:
    """Prioriza pré/pós-mercado; se não encontrar, usa variação regular."""
    if not html:
        return None

    if html.lstrip().startswith(("{", "[")):
        try:
            payload = json.loads(html)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            return _extract_tradingview_percent_json(payload)

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
