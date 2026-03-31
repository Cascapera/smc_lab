import logging
from time import perf_counter
from typing import Optional

from celery import shared_task
from django.utils import timezone

from macro.services import config
from macro.services.collector import execute_cycle
from macro.services.utils import align_measurement_time, is_market_closed
from trader_portal.observability import (
    Timer,
    log_event,
    reset_correlation_id,
    reset_task_id,
    resolve_correlation_id,
    set_correlation_id,
    set_task_id,
)

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,  # 3 tentativas, depois espera próximo agendamento do Beat
)
def collect_macro_cycle(self) -> None:
    """Task Celery que dispara um ciclo de coleta."""
    task_id = getattr(self.request, "id", None)
    if task_id is not None:
        task_id = str(task_id)
    cid = resolve_correlation_id(task_id)
    token_correlation = set_correlation_id(cid)
    token_task = set_task_id(task_id)
    t0 = perf_counter()

    def duration_ms() -> int:
        return int((perf_counter() - t0) * 1000)

    cycle_timer: Optional[Timer] = None
    try:
        if is_market_closed():
            log_event(
                logger,
                event="macro_cycle_skipped",
                message="Market closed window",
                reason="market_closed",
                status="skipped",
                elapsed_ms=duration_ms(),
            )
            return
        measurement_time = align_measurement_time(
            timezone.now(), interval_minutes=config.TARGET_INTERVAL_MINUTES
        )
        with Timer() as ct:
            cycle_timer = ct
            log_event(
                logger,
                event="macro_cycle_started",
                message="Cycle execution",
                measurement_time=measurement_time.isoformat(),
            )
            execute_cycle(measurement_time)
        log_event(
            logger,
            event="macro_cycle_completed",
            message="Cycle finished",
            status="success",
            elapsed_ms=cycle_timer.duration_ms,
            measurement_time=measurement_time.isoformat(),
        )
    except Exception as exc:
        elapsed_ms = cycle_timer.duration_ms if cycle_timer is not None else duration_ms()
        log_event(
            logger,
            event="macro_cycle_failed",
            message="Cycle error",
            status="error",
            elapsed_ms=elapsed_ms,
            error=str(exc),
            exception_type=type(exc).__name__,
            step="collect_macro_cycle",
            level=logging.ERROR,
        )
        if self.request.retries < self.max_retries:
            log_event(
                logger,
                event="macro_retry_scheduled",
                message="Celery autoretry",
                retry_count=self.request.retries + 1,
                reason=str(exc)[:500],
            )
        logger.error(
            "[macro] Erro crítico no ciclo de coleta (tentativa %d/%d): %s",
            self.request.retries + 1,
            self.max_retries + 1,
            str(exc),
            exc_info=True,
        )
        # Re-raise para que o Celery faça o retry (até 3 vezes)
        # Após 3 falhas, para e espera o próximo agendamento do Beat
        raise
    finally:
        reset_correlation_id(token_correlation)
        reset_task_id(token_task)
