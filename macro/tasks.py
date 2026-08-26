import logging
from time import perf_counter
from typing import Optional

from celery import shared_task
from django.core.cache import cache
from django.db.utils import InterfaceError, OperationalError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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

# Trava simples para nao rodar dois ciclos ao mesmo tempo. O timeout garante que
# um worker morto no meio da coleta nao deixe a trava presa para sempre.
#
# Limitacao conhecida: o cache padrao e LocMemCache, que vive na memoria de cada
# processo. Com `--pool=solo --concurrency=1` ha um unico processo executando
# tarefas, entao a trava vale; quando o worker passar para prefork (Fase 3) ou
# houver mais de um worker, e preciso mover o cache para Redis.
CYCLE_LOCK_KEY = "macro:cycle_lock"
CYCLE_LOCK_TIMEOUT_SECONDS = 1800  # 30 min

# Sinal de vida do worker, lido pelo watchdog.
#
# O watchdog usava `celery inspect ping`, que com `--pool=solo` nunca responde:
# ele reiniciava o worker a cada verificacao, incondicionalmente, dando 100% de
# falso positivo. Um monitor que sempre reprova nao detecta travamento algum -
# o travamento real ficaria indistinguivel do normal.
#
# Este carimbo mede o que importa: o worker esta consumindo tarefas? E gravado
# no INICIO de toda execucao, inclusive quando o ciclo e pulado por mercado
# fechado, porque nesse caso a task rodou - so nao coletou.
HEARTBEAT_KEY = "macro:worker_heartbeat"
HEARTBEAT_TTL_SECONDS = 3600


def registrar_heartbeat() -> None:
    """Marca que o worker executou a task agora."""
    try:
        cache.set(HEARTBEAT_KEY, timezone.now().isoformat(), HEARTBEAT_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - heartbeat nao pode derrubar a coleta
        logger.warning("[macro] Falha ao gravar heartbeat: %s", exc)


def idade_do_heartbeat_em_segundos() -> Optional[int]:
    """Ha quantos segundos o worker executou a task pela ultima vez."""
    try:
        marca = cache.get(HEARTBEAT_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[macro] Falha ao ler heartbeat: %s", exc)
        return None
    if not marca:
        return None
    momento = parse_datetime(marca)
    if not momento:
        return None
    return int((timezone.now() - momento).total_seconds())


@shared_task(
    bind=True,
    # `Exception` refazia TODO o scraping (minutos de Playwright) por uma falha
    # de banco na hora de gravar. Pior: cada tentativa recalculava
    # `measurement_time = agora`, entao a retentativa gravava em outro bucket e
    # o original ficava sem MacroScore - um buraco no grafico.
    #
    # Agora so erro transitorio de banco e retentado, e o bucket vem como
    # argumento, para a retentativa gravar exatamente onde a primeira tentaria.
    autoretry_for=(OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def collect_macro_cycle(self, measurement_time_iso: Optional[str] = None) -> None:
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
    lock_acquired = False
    try:
        # Antes de qualquer decisao: se chegamos aqui, o worker esta vivo e
        # consumindo. E o que o watchdog precisa saber.
        registrar_heartbeat()

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

        lock_acquired = cache.add(CYCLE_LOCK_KEY, "1", CYCLE_LOCK_TIMEOUT_SECONDS)
        if not lock_acquired:
            log_event(
                logger,
                event="macro_cycle_skipped",
                message="Another cycle is still running",
                reason="already_running",
                status="skipped",
                elapsed_ms=duration_ms(),
            )
            return

        if measurement_time_iso:
            # Retentativa: reusa o bucket da primeira tentativa.
            measurement_time = parse_datetime(measurement_time_iso)
        else:
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
        # Passa o bucket adiante para a retentativa nao gravar em outro horario.
        if measurement_time is not None and not self.request.args:
            self.request.args = (measurement_time.isoformat(),)
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
        if lock_acquired:
            cache.delete(CYCLE_LOCK_KEY)
        reset_correlation_id(token_correlation)
        reset_task_id(token_task)


@shared_task
def purge_old_macro_variations() -> dict:
    """
    Limpeza diária da tabela de variações.

    `MacroVariation` nunca teve retenção: em produção chegou a 1913 MB e
    1,39 milhão de linhas, 87% do banco, crescendo ~270 MB/mês. Cada backup
    copiava tudo, levando o dump a 2,2 GB.

    Sem autoretry: se falhar, o próximo agendamento tenta de novo. Reprocessar
    uma deleção em lote não traz ganho e só prolongaria o bloqueio na tabela.
    """
    from macro.services.retention import purgar_variacoes_antigas

    with Timer() as t:
        resultado = purgar_variacoes_antigas()

    log_event(
        logger,
        event="macro_retention_completed",
        message="Retention finished",
        status="success",
        elapsed_ms=t.duration_ms,
        found=resultado["encontradas"],
        removed=resultado["removidas"],
        batches=resultado["lotes"],
        retention_days=resultado["dias"],
    )
    return resultado
