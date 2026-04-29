from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trades", "0007_globalaianalyticsrun"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trade",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("region", "Região"),
                    ("passagem", "Passagem"),
                    ("martelo_bf", "Martelo + BF"),
                    ("fffd", "FFFD"),
                    ("padrao", "Padrão"),
                    ("none", "N/D"),
                    ("rocadinha", "Roçadinha"),
                    ("barra_ignorada", "Barra ignorada"),
                    ("gift", "Gift"),
                    ("bota", "BOTA"),
                ],
                max_length=20,
                verbose_name="gatilho",
            ),
        ),
    ]
