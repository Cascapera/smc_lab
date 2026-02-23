from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_profile_discord_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="plan",
            field=models.CharField(
                choices=[
                    ("free", "Free"),
                    ("basic", "Basic"),
                    ("premium", "Premium"),
                    ("premium_plus", "Premium+"),
                ],
                default="free",
                max_length=12,
                verbose_name="plano",
            ),
        ),
    ]
