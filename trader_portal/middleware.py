"""Custom middleware for the trader portal."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class RequestTimingMiddleware:
    """
    Loga o tempo de processamento de cada request.
    Útil para identificar páginas lentas em produção.
    Ative com DJANGO_LOG_REQUEST_TIMING=1 no .env
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if elapsed_ms > 500:  # Só loga requests lentos (>500ms)
            logger.warning(
                "SLOW_REQUEST path=%s method=%s status=%s elapsed_ms=%.0f",
                request.path,
                request.method,
                response.status_code,
                elapsed_ms,
            )
        return response
