import os
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
INVESTING_XHR_ENABLED = True
INVESTING_XHR_CACHE_PATH = ".cache/investing_xhr_cache.json"
INVESTING_XHR_CACHE_TTL_HOURS = 72
TRADINGVIEW_XHR_ENABLED = True
TRADINGVIEW_XHR_CACHE_PATH = ".cache/tradingview_xhr_cache.json"
TRADINGVIEW_XHR_CACHE_TTL_HOURS = 24

# Proxy
PROXY_ENABLED = os.getenv("PROXY_ENABLED", "").strip().lower() in {"1", "true", "yes"}
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()
PROXY_USE_FOR_REQUESTS = os.getenv("PROXY_USE_FOR_REQUESTS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
PROXY_USE_FOR_PLAYWRIGHT = os.getenv("PROXY_USE_FOR_PLAYWRIGHT", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "60000"))
PLAYWRIGHT_WAIT_MS = int(os.getenv("PLAYWRIGHT_WAIT_MS", "4000"))

# Agenda
TARGET_INTERVAL_MINUTES = 5
LEAD_TIME_MINUTES = 2
