"""
Aplicação de plano a partir de eventos do Mercado Pago.

Este módulo é o único lugar que altera `Profile.plan` / `Profile.plan_expires_at`
a partir de um evento externo. Antes, a mesma lógica estava duplicada no webhook
e na página de retorno, sem nenhum controle de repetição:

  - o Mercado Pago reenvia a mesma notificação várias vezes (e em paralelo) até
    receber 200, e cada entrega somava outro período ao plano;
  - a página de retorno aplicava o plano a cada carregamento, então bastava dar
    F5 para estender a assinatura de graça;
  - a página de retorno usava o `user_id` que vinha no pagamento, e não o
    usuário logado, então dava para estender ou revogar o plano de terceiros
    passando um `payment_id` alheio.

Idempotência:
  - Pagamentos: gravamos um `Payment` por `mp_payment_id` (único). O plano só é
    aplicado na primeira transição para `approved`.
  - Assinaturas: o plano só é aplicado quando a `Subscription` entra em
    `authorized`. As renovações seguintes chegam como pagamentos, cada um com
    seu próprio `mp_payment_id`, e caem na regra acima.

A página de retorno continua podendo liberar o plano (é o caminho que o usuário
vê logo após pagar, e não dependemos do webhook chegar antes), mas só para o
próprio usuário logado e sem efeito em recarregamentos.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import PLAN_RANK, Profile

from ..models import Payment, PaymentStatus, Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)

# Resultados possíveis, usados em log e nos testes.
APPLIED = "applied"
ALREADY_PROCESSED = "already_processed"
REVOKED = "revoked"
PLAN_ENDED = "plan_end_scheduled"
IGNORED_NOT_OWNER = "ignored_not_owner"
IGNORED_NO_METADATA = "ignored_no_metadata"
IGNORED_NO_PROFILE = "ignored_no_profile"
IGNORED_STATUS = "ignored_status"
IGNORED_NO_ID = "ignored_no_id"
IGNORED_VALOR_INVALIDO = "ignored_valor_invalido"

_REVOKE_STATUSES = {PaymentStatus.CHARGEDBACK, PaymentStatus.REFUNDED}
_END_STATUSES = {
    SubscriptionStatus.CANCELLED,
    SubscriptionStatus.PAUSED,
    SubscriptionStatus.EXPIRED,
}


def _same_user(user_id: object, restrict_to_user_id: object) -> bool:
    """Compara ids que podem vir como int ou str do metadata do Mercado Pago."""
    if restrict_to_user_id is None:
        return True
    if user_id is None:
        return False
    return str(user_id) == str(restrict_to_user_id)


def _to_decimal(value: object, default: str = "0.00") -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(default)


def _valor_confere(plan_key: str, payment_data: dict) -> tuple[bool, str]:
    """
    Confere se o valor pago corresponde ao plano que o metadata reivindica.

    Sem esta checagem, qualquer pagamento aprovado na conta com
    `metadata.plan_key` liberava o plano correspondente, independentemente do
    valor. O plano oculto `premium_plus_test` custa R$ 5,00 e usa exatamente o
    mesmo caminho do `premium_plus_annual`, de R$ 1.800,00.

    Tolerância de 1 centavo por causa de arredondamento na conversão para float
    que o Mercado Pago faz no payload.
    """
    config = settings.MERCADOPAGO_PLANS.get(plan_key)
    if not config:
        return False, f"plano desconhecido: {plan_key}"

    esperado = _to_decimal(config.get("amount"), "0.00")
    if esperado <= 0:
        return True, ""

    pago = _to_decimal(payment_data.get("transaction_amount"), "0.00")
    if pago < esperado - Decimal("0.01"):
        return False, f"valor pago {pago} menor que {esperado} do plano {plan_key}"

    moeda_paga = (payment_data.get("currency_id") or "").upper()
    moeda_esperada = (settings.MERCADOPAGO_CURRENCY or "BRL").upper()
    if moeda_paga and moeda_paga != moeda_esperada:
        return False, f"moeda {moeda_paga} diferente de {moeda_esperada}"

    return True, ""


# ---------------------------------------------------------------------------
# Pagamentos avulsos e renovações
# ---------------------------------------------------------------------------


@transaction.atomic
def apply_payment_event(
    payment_data: dict,
    *,
    restrict_to_user_id: object = None,
) -> str:
    """
    Processa um pagamento do Mercado Pago.

    `restrict_to_user_id` deve ser preenchido quando a origem do evento é uma
    requisição do usuário (página de retorno): assim um usuário logado não
    consegue processar o pagamento de outra pessoa.
    """
    mp_payment_id = str(payment_data.get("id") or "").strip()
    if not mp_payment_id:
        return IGNORED_NO_ID

    status = payment_data.get("status") or PaymentStatus.PENDING
    metadata = payment_data.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan_key = metadata.get("plan_key")
    plan = metadata.get("plan")

    if not _same_user(user_id, restrict_to_user_id):
        logger.warning(
            "[payments] Pagamento %s ignorado: pertence ao user_id=%s, requisitado por %s",
            mp_payment_id,
            user_id,
            restrict_to_user_id,
        )
        return IGNORED_NOT_OWNER

    if not user_id:
        return IGNORED_NO_METADATA

    profile = (
        Profile.objects.select_for_update().filter(user_id=user_id).first() if user_id else None
    )
    if profile is None:
        logger.warning("[payments] Pagamento %s sem profile (user_id=%s)", mp_payment_id, user_id)
        return IGNORED_NO_PROFILE

    payment, created = Payment.objects.select_for_update().get_or_create(
        mp_payment_id=mp_payment_id,
        defaults={
            "user_id": user_id,
            "plan": plan or "",
            "amount": _to_decimal(payment_data.get("transaction_amount")),
            "currency": payment_data.get("currency_id") or settings.MERCADOPAGO_CURRENCY,
            "status": PaymentStatus.PENDING,
            "external_reference": payment_data.get("external_reference") or "",
        },
    )
    previous_status = payment.status if not created else None

    payment.status = status
    payment.status_detail = str(payment_data.get("status_detail") or "")[:120]
    payment.raw_payload = payment_data
    if not payment.external_reference:
        payment.external_reference = payment_data.get("external_reference") or ""
    payment.save(
        update_fields=["status", "status_detail", "raw_payload", "external_reference", "updated_at"]
    )

    if status == PaymentStatus.APPROVED:
        if previous_status == PaymentStatus.APPROVED:
            # Reentrega do mesmo pagamento: já liberamos o plano por ele.
            return ALREADY_PROCESSED
        if not plan_key or not plan:
            return IGNORED_NO_METADATA

        confere, motivo = _valor_confere(plan_key, payment_data)
        if not confere:
            logger.error(
                "[payments] Pagamento %s NAO liberou plano para user_id=%s: %s",
                mp_payment_id,
                user_id,
                motivo,
            )
            return IGNORED_VALOR_INVALIDO

        _apply_plan(profile, plan_key, plan)
        logger.info(
            "[payments] Plano %s aplicado para user_id=%s (payment %s)",
            plan_key,
            user_id,
            mp_payment_id,
        )
        return APPLIED

    if status in _REVOKE_STATUSES:
        if previous_status in _REVOKE_STATUSES:
            return ALREADY_PROCESSED
        _maybe_revoke_plan(profile, plan)
        logger.info(
            "[payments] Plano revogado para user_id=%s (payment %s, status %s)",
            user_id,
            mp_payment_id,
            status,
        )
        return REVOKED

    return IGNORED_STATUS


# ---------------------------------------------------------------------------
# Assinaturas (preapproval)
# ---------------------------------------------------------------------------


@transaction.atomic
def apply_preapproval_event(
    preapproval_data: dict,
    *,
    restrict_to_user_id: object = None,
) -> str:
    """Processa um evento de assinatura (preapproval) do Mercado Pago."""
    preapproval_id = str(preapproval_data.get("id") or "").strip()
    if not preapproval_id:
        return IGNORED_NO_ID

    status = preapproval_data.get("status") or SubscriptionStatus.PENDING
    external_reference = preapproval_data.get("external_reference") or ""
    metadata = preapproval_data.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan_key = metadata.get("plan_key")
    plan = metadata.get("plan")

    subscription = _find_subscription(
        preapproval_id=preapproval_id,
        external_reference=external_reference,
        user_id=user_id,
        plan_key=plan_key,
        restrict_to_user_id=restrict_to_user_id,
    )

    if subscription is None:
        if restrict_to_user_id is not None and not _same_user(user_id, restrict_to_user_id):
            return IGNORED_NOT_OWNER
        if not (user_id and plan_key and plan):
            return IGNORED_NO_METADATA
        auto_recurring = preapproval_data.get("auto_recurring") or {}
        subscription = Subscription.objects.create(
            user_id=user_id,
            plan=plan,
            plan_key=plan_key,
            amount=_to_decimal(auto_recurring.get("transaction_amount")),
            currency=auto_recurring.get("currency_id") or settings.MERCADOPAGO_CURRENCY,
            status=SubscriptionStatus.PENDING,
            mp_preapproval_id=preapproval_id,
            external_reference=external_reference,
        )

    previous_status = subscription.status

    subscription.mp_preapproval_id = preapproval_id
    subscription.status = status
    subscription.raw_payload = preapproval_data
    if external_reference and not subscription.external_reference:
        subscription.external_reference = external_reference
    subscription.save(
        update_fields=[
            "mp_preapproval_id",
            "status",
            "raw_payload",
            "external_reference",
            "updated_at",
        ]
    )

    if status == previous_status:
        # Reentrega do mesmo evento; nada mudou.
        return ALREADY_PROCESSED

    profile = Profile.objects.select_for_update().filter(user_id=subscription.user_id).first()
    if profile is None:
        return IGNORED_NO_PROFILE

    if status == SubscriptionStatus.AUTHORIZED:
        _apply_plan(profile, subscription.plan_key, subscription.plan)
        logger.info(
            "[payments] Assinatura %s autorizada; plano %s aplicado para user_id=%s",
            preapproval_id,
            subscription.plan_key,
            subscription.user_id,
        )
        return APPLIED

    if status in _END_STATUSES:
        _schedule_plan_end(profile, preapproval_data, subscription.plan)
        return PLAN_ENDED

    return IGNORED_STATUS


def _find_subscription(
    *,
    preapproval_id: str,
    external_reference: str,
    user_id: object,
    plan_key: object,
    restrict_to_user_id: object,
) -> Subscription | None:
    """
    Localiza a assinatura do evento.

    Usa `.filter().first()` (e não `.get()`) de propósito: o bug de concorrência
    corrigido aqui pode ter deixado assinaturas duplicadas para o mesmo
    preapproval em produção.
    """
    base = Subscription.objects.all()
    if restrict_to_user_id is not None:
        base = base.filter(user_id=restrict_to_user_id)

    subscription = base.filter(mp_preapproval_id=preapproval_id).first()
    if subscription:
        return subscription

    if external_reference:
        subscription = base.filter(external_reference=external_reference).first()
        if subscription:
            return subscription

    if user_id and plan_key:
        subscription = (
            base.filter(user_id=user_id, plan_key=plan_key)
            .exclude(status=SubscriptionStatus.CANCELLED)
            .order_by("-created_at")
            .first()
        )
    return subscription


# ---------------------------------------------------------------------------
# Efeitos no perfil
# ---------------------------------------------------------------------------


def _rebaixaria_plano_vigente(profile: Profile, plan: str | None) -> bool:
    """
    True quando o evento e de um plano INFERIOR ao que o usuario tem vigente.

    O perfil guarda um unico par (plan, plan_expires_at), entao qualquer evento
    sobrescrevia os dois. Cenario real: assinante com Basic mensal ativo compra
    Premium+ anual; na cobranca mensal seguinte do Basic, o webhook rebaixava o
    perfil para `basic` e truncava a validade para 30 dias - o usuario perdia
    ~335 dias que ja tinha pago.

    Quando isso acontece, nao mexemos no perfil e registramos em WARNING: e
    sinal de assinaturas sobrepostas, que o suporte precisa ver.
    """
    if not plan:
        return False
    vigente = profile.active_plan()
    return PLAN_RANK.get(plan, 0) < PLAN_RANK.get(vigente, 0)


def _apply_plan(profile: Profile, plan_key: str, plan: str) -> None:
    if _rebaixaria_plano_vigente(profile, plan):
        logger.warning(
            "[payments] Evento do plano %s ignorado para user_id=%s: o perfil tem %s "
            "vigente ate %s. Assinaturas sobrepostas - verifique se ha cobranca duplicada.",
            plan,
            profile.user_id,
            profile.active_plan(),
            profile.plan_expires_at,
        )
        return

    now = timezone.now()
    start_at = (
        profile.plan_expires_at
        if profile.plan == plan and profile.plan_expires_at and profile.plan_expires_at > now
        else now
    )

    profile.plan = plan
    profile.plan_expires_at = start_at + timedelta(days=get_plan_duration(plan_key))
    profile.save(update_fields=["plan", "plan_expires_at"])
    _schedule_discord_sync(profile.user_id)


def get_plan_duration(plan_key: str) -> int:
    plan = settings.MERCADOPAGO_PLANS.get(plan_key, {})
    return int(plan.get("duration_days", 30))


def _maybe_revoke_plan(profile: Profile, plan: str | None = None) -> None:
    """
    Revoga o plano apos chargeback/estorno, se nao houver assinatura ativa.

    `plan` e o plano do evento. Um estorno de Basic nao pode zerar o perfil de
    quem tem Premium+ vigente - antes zerava, porque a funcao so olhava se
    existia alguma Subscription AUTHORIZED (e compras anuais one-time nao criam
    Subscription).
    """
    if _rebaixaria_plano_vigente(profile, plan):
        logger.warning(
            "[payments] Estorno do plano %s nao revoga o perfil de user_id=%s, que tem %s vigente.",
            plan,
            profile.user_id,
            profile.active_plan(),
        )
        return

    active = Subscription.objects.filter(
        user_id=profile.user_id,
        status=SubscriptionStatus.AUTHORIZED,
    ).exists()
    if active:
        return

    profile.plan = "free"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])
    _schedule_discord_sync(profile.user_id)


def _schedule_plan_end(profile: Profile, preapproval_data: dict, plan: str | None = None) -> None:
    if _rebaixaria_plano_vigente(profile, plan):
        logger.warning(
            "[payments] Cancelamento da assinatura %s nao altera o perfil de user_id=%s, "
            "que tem %s vigente.",
            plan,
            profile.user_id,
            profile.active_plan(),
        )
        return

    next_payment_date = preapproval_data.get("next_payment_date")
    if not next_payment_date:
        auto_recurring = preapproval_data.get("auto_recurring") or {}
        next_payment_date = auto_recurring.get("next_payment_date") or auto_recurring.get(
            "end_date"
        )

    next_dt = _parse_mp_datetime(next_payment_date)
    now = timezone.now()
    if next_dt and next_dt > now:
        update_fields: list[str] = []
        if plan and profile.plan != plan:
            profile.plan = plan
            update_fields.append("plan")

        if profile.plan_expires_at and profile.plan_expires_at > next_dt:
            if update_fields:
                profile.save(update_fields=update_fields)
            return

        profile.plan_expires_at = next_dt
        update_fields.append("plan_expires_at")
        profile.save(update_fields=update_fields)
        return

    _maybe_revoke_plan(profile, plan)


def _parse_mp_datetime(value: object | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed and timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    return None


def _schedule_discord_sync(user_id: int) -> None:
    """
    Enfileira a sincronização de roles do Discord depois do commit.

    Com `ATOMIC_REQUESTS=True`, chamar `.delay()` direto faz a task sair antes do
    commit: o worker lê o perfil antigo e aplica a role errada.
    """

    def _enqueue() -> None:
        try:
            from discord_integration.tasks import sync_user_roles

            sync_user_roles.delay(user_id)
        except Exception as exc:
            logger.warning(
                "[payments] Falha ao enfileirar sync_user_roles para user_id=%s: %s",
                user_id,
                exc,
            )

    transaction.on_commit(_enqueue)
