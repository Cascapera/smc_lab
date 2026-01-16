from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_profile_plan_and_expiration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="country",
            field=models.CharField(default="BR", max_length=5, verbose_name="país"),
        ),
    ]
