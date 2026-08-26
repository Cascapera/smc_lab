"""
Idade do último sinal de vida do worker, em segundos.

Existe como management command, e não como `python -c "from macro.tasks import ..."`,
porque aquele one-liner precisava de `django.setup()` para os models carregarem —
sem ele, o import levantava exceção, o watchdog lia string vazia e ficava inerte.
O `manage.py` cuida do setup, então essa classe de erro não se repete aqui.

Saída: um único número.
    >= 0   segundos desde a última execução da task de coleta
    -1     o worker ainda não executou nenhuma task (recém-iniciado)

Uso pelo watchdog:
    docker compose exec -T worker python manage.py worker_heartbeat
"""

from django.core.management.base import BaseCommand

from macro.tasks import idade_do_heartbeat_em_segundos


class Command(BaseCommand):
    help = "Imprime há quantos segundos o worker executou a task de coleta (-1 se nunca)."

    def handle(self, *args, **options):
        idade = idade_do_heartbeat_em_segundos()
        # Sem style e sem texto: a saída é consumida por script.
        self.stdout.write(str(idade if idade is not None else -1))
