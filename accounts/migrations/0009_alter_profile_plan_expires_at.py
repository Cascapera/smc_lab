from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_profile_plan_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="plan_expires_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Defina para expira automaticamente no dia especificado.",
                verbose_name="plano expira em",
            ),
        ),
    ]
