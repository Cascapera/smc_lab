from dataclasses import dataclass
import random
import time
from typing import Dict, Optional

import requests

from macro.services import config
from macro.models import MacroAsset


@dataclass
class FetchOutcome:
    html: Optional[str]
    status: str
    block_reason: Optional[str] = None


def _build_fallback_url(url: str) -> str:
    if url.startswith("https://"):
        stripped = url[len("https://") :]
        return f"{config.FALLBACK_HOST}/https://{stripped}"
    if url.startswith("http://"):
        stripped = url[len("http://") :]
        return f"{config.FALLBACK_HOST}/http://{stripped}"
    return f"{config.FALLBACK_HOST}/https://{url}"


def _fetch_tradingview_playwright(asset: MacroAsset) -> FetchOutcome:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return FetchOutcome(html=None, status="fetch_error", block_reason="playwright_not_installed")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(asset.url, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            if not html:
                return FetchOutcome(html=None, status="no_data", block_reason="empty_html")
            return FetchOutcome(html=html, status="ok")
    except Exception:
        return FetchOutcome(html=None, status="fetch_error", block_reason="playwright_error")


def _fetch_investing_playwright(asset: MacroAsset) -> FetchOutcome:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return FetchOutcome(html=None, status="fetch_error", block_reason="playwright_not_installed")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            user_agent = random.choice(config.USER_AGENTS)
            page = browser.new_page(user_agent=user_agent)
            page.goto(asset.url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()
            browser.close()
            if not html:
                return FetchOutcome(html=None, status="no_data", block_reason="empty_html")
            return FetchOutcome(html=html, status="ok")
    except Exception:
        return FetchOutcome(html=None, status="fetch_error", block_reason="playwright_error")


def _build_headers(attempt: int) -> Dict[str, str]:
    return {
        "User-Agent": config.USER_AGENTS[attempt % len(config.USER_AGENTS)],
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://br.investing.com/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }


def fetch_html(asset: MacroAsset) -> FetchOutcome:
    if asset.source_key == "tradingview":
        outcome = _fetch_tradingview_playwright(asset)
        if outcome.html or outcome.status == "ok":
            return outcome
        return outcome

    block_reason: Optional[str] = None
    session = requests.Session()
    for attempt in range(1, config.MAX_FETCH_ATTEMPTS + 1):
        headers: Dict[str, str] = _build_headers(attempt)
        try:
            response = session.get(asset.url, headers=headers, timeout=config.FETCH_TIMEOUT)
            if response.status_code in (403, 429, 503):
                raise requests.HTTPError(response=response)
            response.raise_for_status()
            if "Just a moment" in response.text or "Verify you are human" in response.text:
                block_reason = "captcha"
            else:
                return FetchOutcome(html=response.text, status="ok")
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (403, 429, 503):
                fallback_url = _build_fallback_url(asset.url)
                try:
                    response = session.get(
                        fallback_url, headers=headers, timeout=config.FETCH_TIMEOUT
                    )
                    response.raise_for_status()
                    if "Just a moment" not in response.text and "Verify you are human" not in response.text:
                        return FetchOutcome(html=response.text, status="ok")
                    block_reason = "captcha"
                except requests.RequestException:
                    block_reason = "fallback_error"
            else:
                block_reason = "fetch_error"
        except requests.RequestException:
            block_reason = "fetch_error"

        if attempt < config.MAX_FETCH_ATTEMPTS:
            delay_min, delay_max = config.RETRY_BACKOFF_RANGE
            time.sleep(random.uniform(delay_min, delay_max))

    if block_reason in ("fallback_error", "captcha", "fetch_error"):
        fallback = _fetch_investing_playwright(asset)
        if fallback.html or fallback.status == "ok":
            return fallback

    status = "blocked" if block_reason in ("fallback_error", "captcha") else "fetch_error"
    return FetchOutcome(html=None, status=status, block_reason=block_reason)
