# Ponto de entrada: inicia o scheduler em background e abre o painel ao vivo
from threading import Thread

from core.services.scheduler import run_forever
from scripts.dashboard_live import launch_dashboard


def main() -> None:
    scheduler_thread = Thread(target=run_forever, daemon=True)
    scheduler_thread.start()
    launch_dashboard()


if __name__ == "__main__":
    main()

