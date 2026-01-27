import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import random
import time
from typing import Dict, Optional, Tuple

import requests
from django.conf import settings

from macro.services import config
from macro.services.parsers import parse_investing_variation, parse_tradingview_variation
from macro.models import MacroAsset

logger = logging.getLogger(__name__)


def _build_proxy_server_url() -> Optional[str]:
    if not config.PROXY_ENABLED or not config.PROXY_SERVER:
        return None
    server = config.PROXY_SERVER
    if "://" not in server:
        server = f"http://{server}"
    if config.PROXY_USERNAME and config.PROXY_PASSWORD:
        scheme, rest = server.split("://", 1)
        return f"{scheme}://{config.PROXY_USERNAME}:{config.PROXY_PASSWORD}@{rest}"
    return server


def _get_requests_proxies() -> Optional[Dict[str, str]]:
    if not config.PROXY_ENABLED or not config.PROXY_USE_FOR_REQUESTS:
        return None
    server = _build_proxy_server_url()
    if not server:
        return None
    return {"http": server, "https": server}


def _get_playwright_proxy() -> Optional[Dict[str, str]]:
    if not config.PROXY_ENABLED or not config.PROXY_USE_FOR_PLAYWRIGHT:
        return None
    server = config.PROXY_SERVER
    if not server:
        return None
    if "://" not in server:
        server = f"http://{server}"
    proxy: Dict[str, str] = {"server": server}
    if config.PROXY_USERNAME and config.PROXY_PASSWORD:
        proxy["username"] = config.PROXY_USERNAME
        proxy["password"] = config.PROXY_PASSWORD
    return proxy


def _classify_playwright_error(exc: Exception) -> Tuple[str, str]:
    """
    Classifica erros do Playwright em categorias específicas.
    Retorna (block_reason, error_type) para melhor diagnóstico.
    """
    error_msg = str(exc).lower()
    error_type = type(exc).__name__
    
    # Bloqueio de IP/proxy
    if any(keyword in error_msg for keyword in [
        "err_aborted",
        "err_connection_refused",
        "err_connection_reset",
        "err_connection_closed",
        "net::err_",
        "403",
        "forbidden",
        "blocked",
        "access denied",
        "frame was detached",
    ]):
        return "playwright_ip_block", error_type
    
    # Timeout
    if any(keyword in error_msg for keyword in [
        "timeout",
        "timed out",
        "waiting for",
        "navigation timeout",
    ]):
        return "playwright_timeout", error_type
    
    # Erro de proxy
    if any(keyword in error_msg for keyword in [
        "proxy",
        "tunnel",
        "socks",
        "proxy authentication",
    ]):
        return "playwright_proxy_error", error_type
    
    # Erro de conexão/rede
    if any(keyword in error_msg for keyword in [
        "connection",
        "network",
        "dns",
        "resolve",
        "unreachable",
        "no internet",
    ]):
        return "playwright_connection_error", error_type
    
    # Erro genérico
    return "playwright_error", error_type


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
            browser = p.chromium.launch(headless=True, proxy=_get_playwright_proxy())
            page = browser.new_page()
            page.goto(asset.url, wait_until="networkidle", timeout=config.PLAYWRIGHT_TIMEOUT_MS)
            if config.PLAYWRIGHT_WAIT_MS > 0:
                page.wait_for_timeout(config.PLAYWRIGHT_WAIT_MS)
            html = page.content()
            browser.close()
            if not html:
                return FetchOutcome(html=None, status="no_data", block_reason="empty_html")
            return FetchOutcome(html=html, status="ok")
    except Exception as exc:
        block_reason, error_type = _classify_playwright_error(exc)
        logger.warning(
            "[macro] Erro Playwright TradingView (%s): %s [%s]",
            asset.name,
            str(exc)[:200],
            block_reason,
        )
        status = "blocked" if block_reason == "playwright_ip_block" else "fetch_error"
        return FetchOutcome(html=None, status=status, block_reason=block_reason)


def _fetch_investing_playwright(asset: MacroAsset) -> FetchOutcome:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return FetchOutcome(html=None, status="fetch_error", block_reason="playwright_not_installed")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, proxy=_get_playwright_proxy())
            user_agent = random.choice(config.USER_AGENTS)
            page = browser.new_page(user_agent=user_agent)
            page.goto(asset.url, wait_until="domcontentloaded", timeout=config.PLAYWRIGHT_TIMEOUT_MS)
            if config.PLAYWRIGHT_WAIT_MS > 0:
                page.wait_for_timeout(config.PLAYWRIGHT_WAIT_MS)
            html = page.content()
            browser.close()
            if not html:
                return FetchOutcome(html=None, status="no_data", block_reason="empty_html")
            return FetchOutcome(html=html, status="ok")
    except Exception as exc:
        block_reason, error_type = _classify_playwright_error(exc)
        logger.warning(
            "[macro] Erro Playwright Investing (%s): %s [%s]",
            asset.name,
            str(exc)[:200],
            block_reason,
        )
        status = "blocked" if block_reason == "playwright_ip_block" else "fetch_error"
        return FetchOutcome(html=None, status=status, block_reason=block_reason)


def _resolve_xhr_cache_path() -> Path:
    cache_path = Path(config.INVESTING_XHR_CACHE_PATH)
    if cache_path.is_absolute():
        return cache_path
    try:
        base_dir = Path(settings.BASE_DIR)
    except Exception:
        base_dir = Path.cwd()
    return base_dir / cache_path


def _load_xhr_cache(cache_path: Path) -> Dict[str, Dict[str, str]]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_xhr_cache(cache_path: Path, cache: Dict[str, Dict[str, str]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _load_investing_xhr_cache() -> Dict[str, Dict[str, str]]:
    cache_path = _resolve_xhr_cache_path()
    return _load_xhr_cache(cache_path)


def _save_investing_xhr_cache(cache: Dict[str, Dict[str, str]]) -> None:
    cache_path = _resolve_xhr_cache_path()
    _save_xhr_cache(cache_path, cache)


def _resolve_tradingview_xhr_cache_path() -> Path:
    cache_path = Path(config.TRADINGVIEW_XHR_CACHE_PATH)
    if cache_path.is_absolute():
        return cache_path
    try:
        base_dir = Path(settings.BASE_DIR)
    except Exception:
        base_dir = Path.cwd()
    return base_dir / cache_path


def _load_tradingview_xhr_cache() -> Dict[str, Dict[str, str]]:
    cache_path = _resolve_tradingview_xhr_cache_path()
    return _load_xhr_cache(cache_path)


def _save_tradingview_xhr_cache(cache: Dict[str, Dict[str, str]]) -> None:
    cache_path = _resolve_tradingview_xhr_cache_path()
    _save_xhr_cache(cache_path, cache)


def _get_cached_investing_xhr_endpoint(asset: MacroAsset) -> Optional[str]:
    cache = _load_investing_xhr_cache()
    entry = cache.get(asset.url)
    if not entry:
        return None
    try:
        updated_at = datetime.fromisoformat(entry.get("updated_at", ""))
    except ValueError:
        return None
    ttl = timedelta(hours=config.INVESTING_XHR_CACHE_TTL_HOURS)
    if datetime.utcnow() - updated_at > ttl:
        return None
    return entry.get("xhr_url")


def _set_cached_investing_xhr_endpoint(asset: MacroAsset, xhr_url: str) -> None:
    cache = _load_investing_xhr_cache()
    cache[asset.url] = {
        "xhr_url": xhr_url,
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save_investing_xhr_cache(cache)


def _clear_cached_investing_xhr_endpoint(asset: MacroAsset) -> None:
    cache = _load_investing_xhr_cache()
    if asset.url in cache:
        cache.pop(asset.url, None)
        _save_investing_xhr_cache(cache)


def _get_cached_tradingview_xhr_endpoint(asset: MacroAsset) -> Optional[str]:
    cache = _load_tradingview_xhr_cache()
    entry = cache.get(asset.url)
    if not entry:
        return None
    try:
        updated_at = datetime.fromisoformat(entry.get("updated_at", ""))
    except ValueError:
        return None
    ttl = timedelta(hours=config.TRADINGVIEW_XHR_CACHE_TTL_HOURS)
    if datetime.utcnow() - updated_at > ttl:
        return None
    return entry.get("xhr_url")


def _set_cached_tradingview_xhr_endpoint(asset: MacroAsset, xhr_url: str) -> None:
    cache = _load_tradingview_xhr_cache()
    cache[asset.url] = {
        "xhr_url": xhr_url,
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save_tradingview_xhr_cache(cache)


def _clear_cached_tradingview_xhr_endpoint(asset: MacroAsset) -> None:
    cache = _load_tradingview_xhr_cache()
    if asset.url in cache:
        cache.pop(asset.url, None)
        _save_tradingview_xhr_cache(cache)


def _discover_tradingview_xhr_endpoint(asset: MacroAsset) -> Optional[Tuple[str, Optional[str]]]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return None

    endpoint_url: Optional[str] = None
    endpoint_body: Optional[str] = None

    def handle_response(response: object) -> None:
        nonlocal endpoint_url, endpoint_body
        if endpoint_url:
            return
        resp = response
        try:
            if resp.request.resource_type != "xhr":
                return
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type:
                return
            body = resp.text()
        except Exception:
            return
        if not body:
            return
        if parse_tradingview_variation(body):
            endpoint_url = resp.url
            endpoint_body = body

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, proxy=_get_playwright_proxy())
            page = browser.new_page()
            page.on("response", handle_response)
            page.goto(asset.url, wait_until="networkidle", timeout=config.PLAYWRIGHT_TIMEOUT_MS)
            if config.PLAYWRIGHT_WAIT_MS > 0:
                page.wait_for_timeout(config.PLAYWRIGHT_WAIT_MS)
            browser.close()
    except Exception as exc:
        block_reason, error_type = _classify_playwright_error(exc)
        logger.warning(
            "[macro] Falha ao descobrir XHR do TradingView (%s): %s [%s - %s]",
            asset.name,
            str(exc)[:200],
            block_reason,
            error_type,
        )
        return None

    if endpoint_url:
        logger.info("[macro] XHR do TradingView descoberto para %s", asset.name)
        return endpoint_url, endpoint_body
    return None


def _fetch_tradingview_xhr(asset: MacroAsset, xhr_url: str) -> FetchOutcome:
    session = requests.Session()
    proxies = _get_requests_proxies()
    if proxies:
        session.proxies.update(proxies)
    headers = _build_headers(1)
    try:
        response = session.get(xhr_url, headers=headers, timeout=config.FETCH_TIMEOUT)
        if response.status_code in (403, 429, 503):
            return FetchOutcome(html=None, status="blocked", block_reason="xhr_block")
        response.raise_for_status()
        if "Just a moment" in response.text or "Verify you are human" in response.text:
            return FetchOutcome(html=None, status="blocked", block_reason="xhr_captcha")
        return FetchOutcome(html=response.text, status="ok")
    except requests.RequestException:
        return FetchOutcome(html=None, status="fetch_error", block_reason="xhr_error")


def _discover_investing_xhr_endpoint(asset: MacroAsset) -> Optional[Tuple[str, Optional[str]]]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return None

    endpoint_url: Optional[str] = None
    endpoint_body: Optional[str] = None

    def handle_response(response: object) -> None:
        nonlocal endpoint_url, endpoint_body
        if endpoint_url:
            return
        resp = response
        try:
            if resp.request.resource_type != "xhr":
                return
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type:
                return
            body = resp.text()
        except Exception:
            return
        if not body:
            return
        if parse_investing_variation(body):
            endpoint_url = resp.url
            endpoint_body = body

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, proxy=_get_playwright_proxy())
            user_agent = random.choice(config.USER_AGENTS)
            page = browser.new_page(user_agent=user_agent)
            page.on("response", handle_response)
            page.goto(asset.url, wait_until="domcontentloaded", timeout=config.PLAYWRIGHT_TIMEOUT_MS)
            if config.PLAYWRIGHT_WAIT_MS > 0:
                page.wait_for_timeout(config.PLAYWRIGHT_WAIT_MS)
            browser.close()
    except Exception as exc:
        block_reason, error_type = _classify_playwright_error(exc)
        logger.warning(
            "[macro] Falha ao descobrir XHR do Investing (%s): %s [%s - %s]",
            asset.name,
            str(exc)[:200],
            block_reason,
            error_type,
        )
        return None

    if endpoint_url:
        logger.info("[macro] XHR do Investing descoberto para %s", asset.name)
        return endpoint_url, endpoint_body
    return None


def _fetch_investing_xhr(asset: MacroAsset, xhr_url: str) -> FetchOutcome:
    session = requests.Session()
    proxies = _get_requests_proxies()
    if proxies:
        session.proxies.update(proxies)
    headers = _build_headers(1)
    try:
        response = session.get(xhr_url, headers=headers, timeout=config.FETCH_TIMEOUT)
        if response.status_code in (403, 429, 503):
            return FetchOutcome(html=None, status="blocked", block_reason="xhr_block")
        response.raise_for_status()
        if "Just a moment" in response.text or "Verify you are human" in response.text:
            return FetchOutcome(html=None, status="blocked", block_reason="xhr_captcha")
        return FetchOutcome(html=response.text, status="ok")
    except requests.RequestException:
        return FetchOutcome(html=None, status="fetch_error", block_reason="xhr_error")


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
        if config.TRADINGVIEW_XHR_ENABLED:
            cached_xhr = _get_cached_tradingview_xhr_endpoint(asset)
            if cached_xhr:
                xhr_outcome = _fetch_tradingview_xhr(asset, cached_xhr)
                if xhr_outcome.html or xhr_outcome.status == "ok":
                    return xhr_outcome
                _clear_cached_tradingview_xhr_endpoint(asset)

        outcome = _fetch_tradingview_playwright(asset)
        if outcome.html or outcome.status == "ok":
            return outcome

        if config.TRADINGVIEW_XHR_ENABLED and outcome.status in ("fetch_error", "no_data"):
            discovery = _discover_tradingview_xhr_endpoint(asset)
            if discovery:
                xhr_url, body = discovery
                _set_cached_tradingview_xhr_endpoint(asset, xhr_url)
                if body:
                    return FetchOutcome(html=body, status="ok")
                xhr_outcome = _fetch_tradingview_xhr(asset, xhr_url)
                if xhr_outcome.html or xhr_outcome.status == "ok":
                    return xhr_outcome

        return outcome

    block_reason: Optional[str] = None
    session = requests.Session()
    proxies = _get_requests_proxies()
    if proxies:
        session.proxies.update(proxies)

    if config.INVESTING_XHR_ENABLED:
        cached_xhr = _get_cached_investing_xhr_endpoint(asset)
        if cached_xhr:
            xhr_outcome = _fetch_investing_xhr(asset, cached_xhr)
            if xhr_outcome.html or xhr_outcome.status == "ok":
                return xhr_outcome
            _clear_cached_investing_xhr_endpoint(asset)

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

    if config.INVESTING_XHR_ENABLED and block_reason in ("fallback_error", "captcha", "fetch_error"):
        discovery = _discover_investing_xhr_endpoint(asset)
        if discovery:
            xhr_url, body = discovery
            _set_cached_investing_xhr_endpoint(asset, xhr_url)
            if body:
                return FetchOutcome(html=body, status="ok")
            xhr_outcome = _fetch_investing_xhr(asset, xhr_url)
            if xhr_outcome.html or xhr_outcome.status == "ok":
                return xhr_outcome

    if block_reason in ("fallback_error", "captcha", "fetch_error"):
        fallback = _fetch_investing_playwright(asset)
        if fallback.html or fallback.status == "ok":
            return fallback

    status = "blocked" if block_reason in ("fallback_error", "captcha") else "fetch_error"
    return FetchOutcome(html=None, status=status, block_reason=block_reason)
