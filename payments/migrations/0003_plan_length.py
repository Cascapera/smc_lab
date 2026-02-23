from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_subscription"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="plan",
            field=models.CharField(
                choices=[
                    ("free", "Free"),
                    ("basic", "Basic"),
                    ("premium", "Premium"),
                    ("premium_plus", "Premium+"),
                ],
                max_length=12,
                verbose_name="plano",
            ),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="plan",
            field=models.CharField(
                choices=[
                    ("free", "Free"),
                    ("basic", "Basic"),
                    ("premium", "Premium"),
                    ("premium_plus", "Premium+"),
                ],
                max_length=12,
                verbose_name="plano",
            ),
        ),
    ]
