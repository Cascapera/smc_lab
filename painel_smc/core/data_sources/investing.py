# Parser específico para páginas do Investing.com
from typing import Optional

from bs4 import BeautifulSoup


def parse_variation(html: str) -> Optional[str]:
    """Localiza a variação percentual atual, priorizando pré/pós-mercado."""
    soup = BeautifulSoup(html, "html.parser")

    # Primeiro tenta capturar a variação exibida no bloco de pré/pós-mercado (classe order-4)
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

    # Se não houver variação indicada para pré/pós-mercado recorre ao span principal padrão
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

