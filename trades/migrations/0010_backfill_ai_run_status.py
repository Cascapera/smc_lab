"""
Classifica as execuções de análise por IA que já existem.

Até aqui não havia campo de status: o limite semanal era calculado por "tem
texto em `result`", e o texto de erro era gravado justamente ali. Ou seja,
usuários cujo relatório falhou (OpenAI fora do ar, chave sem cota) ficaram
bloqueados por 7 dias e viram a mensagem de erro como se fosse o resumo da IA.

Este backfill marca essas execuções como `failed`, o que **destrava esses
usuários imediatamente** — o novo gate só considera execuções `success`.
"""

from django.db import migrations

# Textos que o código antigo gravava em `result` quando, na verdade, falhou.
MARCADORES_DE_FALHA = (
    "Erro na geração do relatório",
    "A IA não retornou texto",
)


def classificar_execucoes(apps, schema_editor):
    for nome_modelo in ("AIAnalyticsRun", "GlobalAIAnalyticsRun"):
        Model = apps.get_model("trades", nome_modelo)

        # Sem texto nenhum: o processo morreu antes de salvar o resultado.
        Model.objects.filter(result="").update(status="failed")

        # Texto de erro gravado como se fosse resultado.
        for marcador in MARCADORES_DE_FALHA:
            Model.objects.filter(result__startswith=marcador).update(status="failed")

        # O que sobrou tem resultado real.
        Model.objects.exclude(status="failed").update(status="success")


def reverter(apps, schema_editor):
    """Sem inverso: o status é informação nova, e voltar tudo para pending
    reintroduziria o bloqueio indevido."""


class Migration(migrations.Migration):
    dependencies = [
        ("trades", "0009_aianalyticsrun_error_detail_aianalyticsrun_status_and_more"),
    ]

    operations = [
        migrations.RunPython(classificar_execucoes, reverter),
    ]
