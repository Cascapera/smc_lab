import logging

from celery import shared_task
from django.utils import timezone

from macro.services import config
from macro.services.collector import execute_cycle
from macro.services.utils import align_measurement_time, is_market_closed


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
    try:
        if is_market_closed():
            logger.info("[macro] Coleta pausada (janela de mercado fechada).")
            return
        measurement_time = align_measurement_time(
            timezone.now(), interval_minutes=config.TARGET_INTERVAL_MINUTES
        )
        logger.info("[macro] Iniciando ciclo para %s", measurement_time)
        execute_cycle(measurement_time)
        logger.info("[macro] Ciclo concluído para %s", measurement_time)
    except Exception as exc:
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