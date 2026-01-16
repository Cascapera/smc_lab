"""
Rotina de agendamento que executa o coletor alguns minutos antes do horário alvo.
"""

import time
from datetime import datetime, timedelta
from typing import Tuple

from core import config
from core.services.collector import execute_cycle


def calculate_next_run_time(reference: datetime) -> Tuple[datetime, datetime]:
    """Retorna (instante_de_execução, horário_alvo) respeitando o intervalo."""
    target = reference.replace(second=0, microsecond=0)
    if target.minute % config.TARGET_INTERVAL_MINUTES != 0 or reference.second > 0:
        delta = (config.TARGET_INTERVAL_MINUTES - (target.minute % config.TARGET_INTERVAL_MINUTES)) % config.TARGET_INTERVAL_MINUTES
        if delta == 0 and reference.second > 0:
            delta = config.TARGET_INTERVAL_MINUTES
        target += timedelta(minutes=delta)
    run_at = target - timedelta(minutes=config.LEAD_TIME_MINUTES)
    if run_at <= reference:
        target += timedelta(minutes=config.TARGET_INTERVAL_MINUTES)
        run_at = target - timedelta(minutes=config.LEAD_TIME_MINUTES)
    return run_at, target


def sleep_until(moment: datetime) -> None:
    """Bloqueia a thread corrente até o instante desejado."""
    while True:
        now = datetime.now()
        remaining = (moment - now).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 1.0))


def run_forever() -> None:
    """Fica em loop disparando ciclos de coleta conforme a agenda."""
    next_run, target = calculate_next_run_time(datetime.now())
    print(f"[scheduler] Próxima execução às {next_run:%Y-%m-%d %H:%M} (alvo {target:%Y-%m-%d %H:%M})")
    while True:
        sleep_until(next_run)
        execute_cycle(target)
        next_run, target = calculate_next_run_time(datetime.now())
        print(f"[scheduler] Próxima execução às {next_run:%Y-%m-%d %H:%M} (alvo {target:%Y-%m-%d %H:%M})")
