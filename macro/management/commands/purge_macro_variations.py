"""
Limpeza manual das variações macro antigas.

Serve para o passivo acumulado: em produção a tabela tinha 1,39 M linhas e
1913 MB. A task diária cuida do dia a dia; este comando é para a primeira
grande purga, que convém acompanhar.

Uso:
    python manage.py purge_macro_variations --dry-run        # só conta
    python manage.py purge_macro_variations --days 90        # apaga de fato
    python manage.py purge_macro_variations --days 30 --batch-size 2000
"""

from django.core.management.base import BaseCommand, CommandError

from macro.services.retention import (
    TAMANHO_LOTE_PADRAO,
    dias_de_retencao,
    purgar_variacoes_antigas,
)


class Command(BaseCommand):
    help = "Remove variações macro anteriores ao período de retenção, em lotes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=f"Dias a manter (padrão: {dias_de_retencao()}, de MACRO_VARIATION_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas conta quantas linhas seriam removidas, sem apagar nada.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=TAMANHO_LOTE_PADRAO,
            help=(
                f"Linhas por lote (padrão: {TAMANHO_LOTE_PADRAO}). Lotes menores "
                "seguram menos a tabela, que recebe escrita a cada 5 minutos."
            ),
        )

    def handle(self, *args, **options):
        dias = options["days"]
        dry_run = options["dry_run"]
        tamanho_lote = options["batch_size"]

        if tamanho_lote < 1:
            raise CommandError("--batch-size precisa ser pelo menos 1.")

        try:
            resultado = purgar_variacoes_antigas(
                dias=dias,
                tamanho_lote=tamanho_lote,
                dry_run=dry_run,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Retenção:   {resultado['dias']} dias")
        self.stdout.write(f"Corte em:   {resultado['corte']}")
        self.stdout.write(f"Encontradas: {resultado['encontradas']} variações")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Simulação: nada foi removido. Rode sem --dry-run para apagar.")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Removidas:   {resultado['removidas']} em {resultado['lotes']} lote(s)"
            )
        )
        if resultado["removidas"]:
            self.stdout.write(
                "Observação: o espaço volta a ser reutilizado pelo Postgres, mas só é "
                "devolvido ao sistema de arquivos com VACUUM FULL (que trava a tabela). "
                "O ganho imediato aparece no tamanho dos backups."
            )
