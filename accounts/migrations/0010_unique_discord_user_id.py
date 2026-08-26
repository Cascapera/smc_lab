"""
Unicidade de `discord_user_id` (A6).

A migração de dados roda antes da constraint porque o banco de produção pode já
ter duplicados — e aí o `AddConstraint` falharia no meio do deploy. A regra de
desempate está em `accounts/discord_links.py`.
"""

from django.db import migrations, models

from accounts.discord_links import resolve_duplicate_discord_links


def desvincular_duplicados(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    resolve_duplicate_discord_links(Profile)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_alter_profile_plan_expires_at"),
    ]

    operations = [
        migrations.RunPython(desvincular_duplicados, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="profile",
            constraint=models.UniqueConstraint(
                fields=["discord_user_id"],
                # Conta sem Discord grava string vazia, não NULL: sem a condição
                # a constraint proibiria a segunda conta sem Discord do sistema.
                condition=~models.Q(discord_user_id=""),
                name="perfil_discord_user_id_unico",
            ),
        ),
    ]
