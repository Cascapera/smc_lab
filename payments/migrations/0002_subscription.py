from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("free", "Free"), ("basic", "Basic"), ("premium", "Premium")], max_length=10, verbose_name="plano")),
                ("plan_key", models.CharField(max_length=30, verbose_name="plano chave")),
                ("amount", models.DecimalField(decimal_places=2, default=0.0, max_digits=10, verbose_name="valor")),
                ("currency", models.CharField(default="BRL", max_length=10, verbose_name="moeda")),
                ("status", models.CharField(choices=[("pending", "Pendente"), ("authorized", "Autorizado"), ("paused", "Pausado"), ("cancelled", "Cancelado"), ("expired", "Expirado")], default="pending", max_length=20, verbose_name="status")),
                ("mp_plan_id", models.CharField(blank=True, max_length=120, verbose_name="plano MP")),
                ("mp_preapproval_id", models.CharField(blank=True, max_length=120, verbose_name="assinatura MP")),
                ("external_reference", models.CharField(blank=True, max_length=120, verbose_name="referência")),
                ("raw_payload", models.JSONField(blank=True, null=True, verbose_name="payload")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "assinatura",
                "verbose_name_plural": "assinaturas",
                "ordering": ("-created_at",),
            },
        ),
    ]
