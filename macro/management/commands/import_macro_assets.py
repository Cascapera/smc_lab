import pathlib

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from macro.models import MacroAsset, SourceChoices


class Command(BaseCommand):
    help = "Importa ativos macro a partir de uma planilha Excel (colunas: Ativo, ValorBase, URL, opcional Categoria)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="painel_smc/data/planilha_referencia.xlsx",
            help="Caminho para o arquivo Excel de referência.",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Zera a tabela antes de importar.",
        )

    def handle(self, *args, **options):
        path = pathlib.Path(options["path"]).resolve()
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        df = pd.read_excel(path)
        missing = {"Ativo", "ValorBase", "URL"} - set(df.columns)
        if missing:
            raise CommandError(f"Colunas ausentes na planilha: {missing}")

        if options["truncate"]:
            MacroAsset.objects.all().delete()
            self.stdout.write(self.style.WARNING("Tabela MacroAsset limpa."))

        created = 0
        updated = 0
        for _, row in df.iterrows():
            name = str(row["Ativo"]).strip()
            value_base = float(row["ValorBase"])
            url = str(row["URL"]).strip()
            category = ""
            if "Categoria" in df.columns:
                raw_cat = row["Categoria"]
                if pd.notna(raw_cat):
                    category = str(raw_cat).strip()
            source_key = (
                SourceChoices.INVESTING if "investing.com" in url else SourceChoices.TRADINGVIEW
            )

            obj, is_created = MacroAsset.objects.update_or_create(
                name=name,
                defaults={
                    "value_base": value_base,
                    "url": url,
                    "source_key": source_key,
                    "category": category,
                    "active": True,
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Importação concluída: {created} criados, {updated} atualizados (arquivo: {path})"
            )
        )
