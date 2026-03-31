"""
Structured logging helpers: correlation_id (ContextVar), JSON log lines, Timer.
Stdlib only; safe for Celery workers.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar, Token
from typing import Any, Dict, Optional

_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_task_id: ContextVar[Optional[str]] = ContextVar("task_id", default=None)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def get_correlation_id() -> Optional[str]:
    return _correlation_id.get()


def set_correlation_id(value: str) -> Token:
    return _correlation_id.set(value)


def reset_correlation_id(token: Token) -> None:
    _correlation_id.reset(token)


def get_task_id() -> Optional[str]:
    return _task_id.get()


def set_task_id(value: Optional[str]) -> Token:
    return _task_id.set(value)


def reset_task_id(token: Token) -> None:
    _task_id.reset(token)


def resolve_correlation_id(task_id: Optional[str]) -> str:
    """Prefer existing context, else Celery task id, else a new UUID."""
    existing = get_correlation_id()
    if existing:
        return existing
    if task_id:
        return str(task_id)
    return new_correlation_id()


class Timer:
    """Wall-clock elapsed time in milliseconds (set on context exit)."""

    __slots__ = ("_t0", "duration_ms")

    def __init__(self) -> None:
        self.duration_ms = 0
        self._t0 = 0.0

    def __enter__(self) -> Timer:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.duration_ms = int((time.perf_counter() - self._t0) * 1000)
        return False


def log_event(
    logger: logging.Logger,
    *,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload: Dict[str, Any] = {"event": event}
    cid = get_correlation_id()
    if cid:
        payload["correlation_id"] = cid
    tid = get_task_id()
    if tid:
        payload["task_id"] = tid
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    try:
        line = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        line = json.dumps(
            {"event": event, "error": "log_event_serialize_failed"},
            default=str,
        )
    try:
        logger.log(level, line)
    except Exception:
        # Não interromper o chamador por falha de handler/logging.
        pass
