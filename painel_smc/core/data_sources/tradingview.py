# Parser específico para páginas do TradingView
from typing import Optional

from bs4 import BeautifulSoup


def _normalize(text: str) -> str:
    """Normaliza o texto percentual mantendo o sufixo % e sinal."""
    cleaned = (
        text.replace("\u2212", "-")  # sinal de menos unicode
        .replace("\u00a0", "")
        .strip()
    )
    if not cleaned.endswith("%"):
        cleaned = f"{cleaned}%"
    return cleaned


def parse_variation(html: str) -> Optional[str]:
    """
    Prioriza pré/pós-mercado; se não encontrar, usa variação regular.

    - Pré/pós: <span class="js-symbol-ext-hrs-change-pt">+0,34%</span>
    - Regular: <span class="js-symbol-change-pt">−0,08%</span>
    """
    soup = BeautifulSoup(html, "html.parser")

    ext_span = soup.find("span", class_="js-symbol-ext-hrs-change-pt")
    if ext_span and ext_span.get_text(strip=True):
        return f"EXT:{_normalize(ext_span.get_text(strip=True))}"

    reg_span = soup.find("span", class_="js-symbol-change-pt")
    if reg_span and reg_span.get_text(strip=True):
        return f"REG:{_normalize(reg_span.get_text(strip=True))}"

    return None
