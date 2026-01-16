"""Eventos compartilhados para sinalizar término de coleta e disparar atualizações."""
import threading

# Evento global indicando que há dados novos prontos para serem consumidos pelo dashboard
data_ready_event = threading.Event()


def signal_data_ready() -> None:
    """Sinaliza que um ciclo de coleta terminou e os dados foram gravados."""
    data_ready_event.set()


def consume_data_ready() -> bool:
    """
    Limpa o sinal, retornando True se estava setado.
    Útil para evitar reprocessar o mesmo ciclo.
    """
    if data_ready_event.is_set():
        data_ready_event.clear()
        return True
    return False

