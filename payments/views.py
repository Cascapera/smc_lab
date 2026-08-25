from __future__ import annotations

import json
import logging

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from .models import Subscription, SubscriptionStatus
from .services.mercadopago import (
    create_preapproval,
    create_preapproval_plan,
    create_preference,
    extract_payment_id,
    fetch_payment,
    fetch_preapproval,
    validate_webhook_signature,
)
from .services.plans import apply_payment_event, apply_preapproval_event

logger = logging.getLogger(__name__)


class PlanListView(TemplateView):
    template_name = "payments/plans.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["plans"] = {
            key: value
            for key, value in settings.MERCADOPAGO_PLANS.items()
            if not value.get("hidden")
        }
        context["currency"] = settings.MERCADOPAGO_CURRENCY
        context["trial_days"] = settings.MERCADOPAGO_TRIAL_DAYS
        context["profile"] = getattr(self.request.user, "profile", None)
        return context


class CreateCheckoutView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, plan: str) -> HttpResponse:
        plan_key = plan.lower()
        if plan_key not in settings.MERCADOPAGO_PLANS:
            messages.error(request, "Plano inválido.")
            return redirect(reverse("payments:plans"))

        config = settings.MERCADOPAGO_PLANS[plan_key]
        plan_name = config["plan"]
        amount = config["amount"]
        currency = settings.MERCADOPAGO_CURRENCY
        frequency = config["frequency"]
        frequency_type = config["frequency_type"]
        success_url = request.build_absolute_uri(reverse("payments:return"))
        notification_url = request.build_absolute_uri(reverse("payments:webhook"))
        public_back_url = settings.MERCADOPAGO_BACK_URL or success_url
        public_webhook_url = settings.MERCADOPAGO_WEBHOOK_URL or notification_url

        if "localhost" in public_back_url or "127.0.0.1" in public_back_url:
            messages.error(
                request,
                "Configure MERCADOPAGO_BACK_URL com a URL pública (ngrok) no .env.",
            )
            return redirect(reverse("payments:plans"))
        external_reference = (
            f"user:{request.user.id}|plan:{plan_key}|ts:{int(timezone.now().timestamp())}"
        )

        payer_email = request.user.email
        if settings.MERCADOPAGO_USE_SANDBOX and settings.MERCADOPAGO_TEST_PAYER_EMAIL:
            payer_email = settings.MERCADOPAGO_TEST_PAYER_EMAIL

        if not settings.MERCADOPAGO_ACCESS_TOKEN:
            messages.error(request, "Token do Mercado Pago não configurado.")
            return redirect(reverse("payments:plans"))

        billing_type = config.get("billing_type", "subscription")
        if billing_type == "one_time":
            preference_payload = {
                "items": [
                    {
                        "title": config["label"],
                        "quantity": 1,
                        "unit_price": float(amount),
                        "currency_id": currency,
                    }
                ],
                "payer": {"email": payer_email},
                "back_urls": {
                    "success": public_back_url,
                    "failure": public_back_url,
                    "pending": public_back_url,
                },
                "auto_return": "approved",
                "external_reference": external_reference,
                "metadata": {
                    "user_id": request.user.id,
                    "plan": plan_name,
                    "plan_key": plan_key,
                    "mode": "one_time",
                },
                "notification_url": public_webhook_url,
                "payment_methods": {"installments": 12},
            }

            try:
                preference = create_preference(preference_payload)
            except Exception as exc:
                messages.error(
                    request,
                    f"Não foi possível iniciar o pagamento. {exc}",
                )
                return redirect(reverse("payments:plans"))

            init_point = preference.get("init_point")
            return redirect(init_point)

        preapproval_payload = {
            "reason": config["label"],
            "payer_email": payer_email,
            "back_url": public_back_url,
            "external_reference": external_reference,
            "metadata": {"user_id": request.user.id, "plan": plan_name, "plan_key": plan_key},
            "notification_url": public_webhook_url,
            "auto_recurring": {
                "frequency": frequency,
                "frequency_type": frequency_type,
                "transaction_amount": float(amount),
                "currency_id": currency,
                "start_date": timezone.now().isoformat(),
            },
        }
        if settings.MERCADOPAGO_TRIAL_DAYS > 0:
            preapproval_payload["trial_period"] = {
                "frequency": settings.MERCADOPAGO_TRIAL_DAYS,
                "frequency_type": "days",
            }

        try:
            preapproval = create_preapproval(preapproval_payload)
        except Exception as exc:
            messages.error(
                request,
                f"Não foi possível iniciar a assinatura. {exc}",
            )
            return redirect(reverse("payments:plans"))

        Subscription.objects.create(
            user=request.user,
            plan=plan_name,
            plan_key=plan_key,
            amount=amount,
            currency=currency,
            status=SubscriptionStatus.PENDING,
            mp_plan_id="",
            mp_preapproval_id=preapproval.get("id", ""),
            external_reference=external_reference,
            raw_payload=preapproval,
        )

        init_point = preapproval.get("init_point")
        return redirect(init_point)


def _erro_e_transitorio(exc: Exception) -> bool:
    """
    Diz se vale a pena o Mercado Pago reenviar a notificacao.

    Timeout, queda de conexao, 5xx e 429 sao instabilidade do lado deles: se
    respondermos 200, o evento e descartado para sempre e o pagamento nunca
    libera o plano - foi assim que ficou ate agora. Ja um 404 (id que nao existe)
    e permanente: reenviar so gera ruido.
    """
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        codigo = exc.response.status_code
        return codigo >= 500 or codigo == 429
    # Erro que nao reconhecemos: preferimos que o MP tente de novo a perder o evento.
    return not isinstance(exc, requests.HTTPError)


class PaymentReturnView(LoginRequiredMixin, TemplateView):
    """
    Página que o usuário vê ao voltar do Mercado Pago.

    Continua podendo liberar o plano (não dependemos de o webhook ter chegado
    antes), mas agora com duas garantias que faltavam:

      - só processa eventos do **próprio usuário logado**. Antes, o plano era
        aplicado no `user_id` que vinha no pagamento, então dava para estender
        ou revogar o plano de terceiros passando um `payment_id` alheio;
      - passa pelo serviço idempotente, então recarregar a página não soma mais
        outro período ao plano (antes, 12 F5 viravam 12 meses de graça).
    """

    template_name = "payments/return.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get("status") or "pending"
        user_id = self.request.user.id

        preapproval_id = self.request.GET.get("preapproval_id") or self.request.GET.get("id")
        if not preapproval_id:
            preapproval_id = (
                Subscription.objects.filter(user=self.request.user)
                .exclude(mp_preapproval_id="")
                .order_by("-created_at")
                .values_list("mp_preapproval_id", flat=True)
                .first()
            )

        if preapproval_id:
            try:
                preapproval_data = fetch_preapproval(preapproval_id)
                preapproval_data.setdefault("id", preapproval_id)
                status = preapproval_data.get("status") or status
                result = apply_preapproval_event(preapproval_data, restrict_to_user_id=user_id)
                logger.info(
                    "[payments] Retorno: preapproval %s -> %s (user_id=%s)",
                    preapproval_id,
                    result,
                    user_id,
                )
            except Exception as exc:
                logger.exception(
                    "[payments] Erro ao processar preapproval %s no retorno: %s",
                    preapproval_id,
                    exc,
                )

        payment_id = extract_payment_id(self.request.GET, {})
        if payment_id:
            try:
                payment_data = fetch_payment(payment_id)
                payment_data.setdefault("id", payment_id)
                status = payment_data.get("status") or status
                result = apply_payment_event(payment_data, restrict_to_user_id=user_id)
                logger.info(
                    "[payments] Retorno: payment %s -> %s (user_id=%s)",
                    payment_id,
                    result,
                    user_id,
                )
            except Exception as exc:
                logger.exception(
                    "[payments] Erro ao processar payment %s no retorno: %s",
                    payment_id,
                    exc,
                )

        context["status"] = status
        return context


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class MercadoPagoWebhookView(View):
    """
    Recebe as notificações do Mercado Pago.

    O MP reenvia a mesma notificação várias vezes (e em paralelo) até receber um
    200 rápido. Toda a aplicação de plano passa por `payments.services.plans`,
    que garante que cada pagamento/assinatura só produza efeito uma vez.
    """

    # Topics conhecidos hoje. Os demais são logados em WARNING para sabermos
    # exatamente o que a conta recebe antes de mapear os formatos novos
    # (`subscription_preapproval`, `subscription_authorized_payment`).
    KNOWN_TOPICS = {"preapproval", "payment"}

    def post(self, request: HttpRequest) -> HttpResponse:
        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except json.JSONDecodeError:
            payload = {}

        data_id = extract_payment_id(request.GET, payload)
        webhook_secret = getattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "") or ""
        if data_id and webhook_secret:
            x_signature = request.headers.get("x-signature")
            x_request_id = request.headers.get("x-request-id")
            if not validate_webhook_signature(x_signature, x_request_id, data_id, webhook_secret):
                logger.warning("[payments] Webhook assinatura inválida, rejeitando.")
                return HttpResponse(status=401)
        elif not webhook_secret:
            logger.warning(
                "[payments] MERCADOPAGO_WEBHOOK_SECRET não configurado: "
                "webhook aceito sem validar assinatura."
            )

        topic = payload.get("type") or payload.get("topic") or request.GET.get("topic")
        if topic not in self.KNOWN_TOPICS:
            logger.warning(
                "[payments] Webhook com topic desconhecido: %r (data_id=%s). "
                "Tratando como pagamento.",
                topic,
                data_id,
            )

        if topic == "preapproval":
            if not data_id:
                return HttpResponse(status=200)
            try:
                preapproval_data = fetch_preapproval(data_id)
            except Exception as exc:
                logger.exception(
                    "[payments] Erro ao buscar preapproval %s no webhook: %s", data_id, exc
                )
                if _erro_e_transitorio(exc):
                    # 503 faz o Mercado Pago reenviar com backoff. Responder 200
                    # aqui descartava o evento e o plano nunca era liberado.
                    return HttpResponse(status=503)
                return HttpResponse(status=200)

            preapproval_data.setdefault("id", data_id)
            result = apply_preapproval_event(preapproval_data)
            logger.info("[payments] Webhook: preapproval %s -> %s", data_id, result)
            return HttpResponse(status=200)

        if not data_id:
            return HttpResponse(status=200)

        try:
            payment_data = fetch_payment(data_id)
        except Exception as exc:
            logger.exception("[payments] Erro ao buscar payment %s no webhook: %s", data_id, exc)
            if _erro_e_transitorio(exc):
                return HttpResponse(status=503)
            return HttpResponse(status=200)

        payment_data.setdefault("id", data_id)
        result = apply_payment_event(payment_data)
        logger.info("[payments] Webhook: payment %s -> %s", data_id, result)
        return HttpResponse(status=200)


def _ensure_preapproval_plan(plan_key: str, config: dict, currency: str, back_url: str) -> str:
    existing = (
        Subscription.objects.filter(plan_key=plan_key)
        .exclude(mp_plan_id="")
        .values_list("mp_plan_id", flat=True)
        .first()
    )
    if existing:
        return existing

    payload = {
        "reason": f"Assinatura {config['label']}",
        "status": "active",
        "auto_recurring": {
            "frequency": config["frequency"],
            "frequency_type": config["frequency_type"],
            "transaction_amount": float(config["amount"]),
            "currency_id": currency,
        },
        "back_url": back_url,
        "payment_methods_allowed": {"payment_types": [{"id": "credit_card"}]},
        "trial_period": {
            "frequency": settings.MERCADOPAGO_TRIAL_DAYS,
            "frequency_type": "days",
        },
    }

    response = create_preapproval_plan(payload)
    return response.get("id")
