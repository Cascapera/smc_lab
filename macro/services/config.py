from typing import Tuple

# Rede / scraping
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

FETCH_DELAY_RANGE: Tuple[float, float] = (0.5, 1.0)
RETRY_BACKOFF_RANGE: Tuple[float, float] = (1.0, 2.5)
MAX_FETCH_ATTEMPTS = 3
FETCH_TIMEOUT = 25
FALLBACK_HOST = "https://r.jina.ai"

# Agenda
TARGET_INTERVAL_MINUTES = 5
LEAD_TIME_MINUTES = 2
