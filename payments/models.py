from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from accounts.models import Plan


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    APPROVED = "approved", "Aprovado"
    REJECTED = "rejected", "Recusado"
    CANCELLED = "cancelled", "Cancelado"
    REFUNDED = "refunded", "Reembolsado"
    CHARGEDBACK = "chargeback", "Chargeback"


class SubscriptionStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    AUTHORIZED = "authorized", "Autorizado"
    PAUSED = "paused", "Pausado"
    CANCELLED = "cancelled", "Cancelado"
    EXPIRED = "expired", "Expirado"


class Payment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    plan = models.CharField("plano", max_length=12, choices=Plan.choices)
    amount = models.DecimalField(
        "valor",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField("moeda", max_length=10, default="BRL")
    status = models.CharField(
        "status",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    status_detail = models.CharField("detalhe", max_length=120, blank=True)
    mp_preference_id = models.CharField("preference id", max_length=120, blank=True)
    mp_payment_id = models.CharField("payment id", max_length=120, blank=True)
    external_reference = models.CharField("referência", max_length=120, blank=True)
    raw_payload = models.JSONField("payload", blank=True, null=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["mp_payment_id"]),
            models.Index(fields=["external_reference"]),
        ]
        constraints = [
            # Chave de idempotência: o Mercado Pago reenvia a mesma notificação
            # várias vezes. Um pagamento só pode virar uma linha, para o plano ser
            # aplicado uma vez só. Condicional porque `mp_payment_id` é opcional
            # (pagamento ainda sem id do MP fica com string vazia).
            models.UniqueConstraint(
                fields=["mp_payment_id"],
                condition=~models.Q(mp_payment_id=""),
                name="uniq_payment_mp_payment_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.plan} - {self.status}"


class Subscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.CharField("plano", max_length=12, choices=Plan.choices)
    plan_key = models.CharField("plano chave", max_length=30)
    amount = models.DecimalField(
        "valor",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField("moeda", max_length=10, default="BRL")
    status = models.CharField(
        "status",
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING,
    )
    mp_plan_id = models.CharField("plano MP", max_length=120, blank=True)
    mp_preapproval_id = models.CharField("assinatura MP", max_length=120, blank=True)
    external_reference = models.CharField("referência", max_length=120, blank=True)
    # Data da próxima cobrança segundo o Mercado Pago. Guardada para o suporte
    # conseguir conferir a validade do plano contra o calendário real de cobrança
    # sem precisar consultar a API.
    next_payment_date = models.DateTimeField("próxima cobrança", null=True, blank=True)
    raw_payload = models.JSONField("payload", blank=True, null=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "assinatura"
        verbose_name_plural = "assinaturas"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["mp_preapproval_id"]),
            models.Index(fields=["external_reference"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.plan_key} - {self.status}"
