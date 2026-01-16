from django.db import migrations, models

import accounts.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_profile_current_balance_profile_initial_balance_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="plan",
            field=models.CharField(
                choices=accounts.models.Plan.choices,
                default=accounts.models.Plan.FREE,
                max_length=10,
                verbose_name="plano",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="plan_expires_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Defina para expirará automaticamente no dia especificado.",
                null=True,
                verbose_name="plano expira em",
            ),
        ),
    ]
