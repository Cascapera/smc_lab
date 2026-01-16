from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_profile_country_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="country",
            field=models.CharField(default="BR", max_length=50, verbose_name="país"),
        ),
    ]
