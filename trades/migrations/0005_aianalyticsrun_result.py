# Generated manually - campo result para guardar resposta da IA

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trades", "0004_aianalyticsrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="aianalyticsrun",
            name="result",
            field=models.TextField(blank=True, default="", verbose_name="resultado da análise"),
        ),
    ]
