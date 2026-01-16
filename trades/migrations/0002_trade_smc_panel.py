from django.db import migrations, models

import trades.models


class Migration(migrations.Migration):

    dependencies = [
        ("trades", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="trade",
            name="smc_panel",
            field=models.CharField(
                choices=trades.models.SMCPanel.choices,
                default=trades.models.SMCPanel.NEUTRAL,
                max_length=15,
                verbose_name="Painel SMC",
            ),
        ),
    ]
