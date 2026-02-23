from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("free", "Free"), ("basic", "Basic"), ("premium", "Premium")], max_length=10, verbose_name="plano")),
                ("amount", models.DecimalField(decimal_places=2, default=0.0, max_digits=10, verbose_name="valor")),
                ("currency", models.CharField(default="BRL", max_length=10, verbose_name="moeda")),
                ("status", models.CharField(choices=[("pending", "Pendente"), ("approved", "Aprovado"), ("rejected", "Recusado"), ("cancelled", "Cancelado"), ("refunded", "Reembolsado"), ("chargeback", "Chargeback")], default="pending", max_length=20, verbose_name="status")),
                ("status_detail", models.CharField(blank=True, max_length=120, verbose_name="detalhe")),
                ("mp_preference_id", models.CharField(blank=True, max_length=120, verbose_name="preference id")),
                ("mp_payment_id", models.CharField(blank=True, max_length=120, verbose_name="payment id")),
                ("external_reference", models.CharField(blank=True, max_length=120, verbose_name="referência")),
                ("raw_payload", models.JSONField(blank=True, null=True, verbose_name="payload")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="payments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "pagamento",
                "verbose_name_plural": "pagamentos",
                "ordering": ("-created_at",),
            },
        ),
    ]
