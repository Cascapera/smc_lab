import logging

from celery import shared_task
from django.utils import timezone

from macro.services import config
from macro.services.collector import execute_cycle
from macro.services.utils import align_measurement_time


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def collect_macro_cycle(self) -> None:
    """Task Celery que dispara um ciclo de coleta."""
    measurement_time = align_measurement_time(
        timezone.now(), interval_minutes=config.TARGET_INTERVAL_MINUTES
    )
    logger.info("[macro] Iniciando ciclo para %s", measurement_time)
    execute_cycle(measurement_time)
    logger.info("[macro] Ciclo concluído para %s", measurement_time)