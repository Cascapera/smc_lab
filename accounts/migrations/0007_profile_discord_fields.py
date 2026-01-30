from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_profile_country_length_extend"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="discord_user_id",
            field=models.CharField(blank=True, max_length=30, verbose_name="discord id"),
        ),
        migrations.AddField(
            model_name="profile",
            name="discord_username",
            field=models.CharField(blank=True, max_length=120, verbose_name="discord usuário"),
        ),
        migrations.AddField(
            model_name="profile",
            name="discord_connected_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="discord conectado em"
            ),
        ),
    ]
