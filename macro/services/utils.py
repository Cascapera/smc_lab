import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from django.utils import timezone


def align_measurement_time(dt: datetime, interval_minutes: int = 5) -> datetime:
    """Alinha para o múltiplo inferior do intervalo (ex.: 12:07 -> 12:05)."""
    local_dt = timezone.localtime(dt)
    minute = (local_dt.minute // interval_minutes) * interval_minutes
    return local_dt.replace(minute=minute, second=0, microsecond=0)


def extract_relevant_text(html: str, max_chars: int = 6000) -> str:
    """Extrai texto relevante do HTML (remove scripts/estilos)."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
    keywords = ("%","Pre-Market","After Hours","After-Hours","Previous Close")
    filtered = [line for line in lines if any(keyword in line for keyword in keywords)]
    if not filtered:
        filtered = lines[:120]
    return "\n".join(filtered)[:max_chars]


def parse_variation_percent(value: Optional[str]) -> Optional[float]:
    """Converte string percentual para decimal (ex.: '0,36%' -> 0.0036)."""
    if value is None:
        return None
    text = (
        str(value)
        .strip()
        .replace("\u2212", "-")  # Unicode minus → ASCII
        .replace(" ", "")
    )
    if not text:
        return None

    match = re.search(r"([-+]?[\d.,]+)%", text)
    if not match:
        return None

    number = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(number) / 100.0
    except ValueError:
        return None


def is_market_closed(dt: Optional[datetime] = None) -> bool:
    """Retorna True quando a janela de coleta deve pausar (sex 19h até dom 19h)."""
    local_dt = timezone.localtime(dt or timezone.now())
    weekday = local_dt.weekday()  # 0=Mon .. 6=Sun
    hour = local_dt.hour
    if weekday == 4 and hour >= 19:
        return True
    if weekday == 5:
        return True
    if weekday == 6 and hour < 19:
        return True
    return False
