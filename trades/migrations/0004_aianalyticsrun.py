# Generated manually for Analytics avançado por IA (limite 1x/semana)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trades", "0003_alter_trade_entry_type_alter_trade_trend"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIAnalyticsRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_at", models.DateTimeField(auto_now_add=True, verbose_name="solicitado em")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_analytics_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "execução análise IA",
                "verbose_name_plural": "execuções análise IA",
                "ordering": ("-requested_at",),
            },
        ),
    ]
