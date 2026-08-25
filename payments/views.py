from __future__ import annotations

import json
import logging
import uuid

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
    fetch_authorized_payment,
    fetch_payment,
    fetch_preapproval,
    validate_webhook_signature,
)
from .services.plans import apply_payment_event, apply_preapproval_event

logger = logging.getLogger(__name__)


def _link_de_checkout(recurso: dict) -> str | None:
    """
    Link para onde mandar o usuário.

    Em sandbox o campo é `sandbox_init_point`; usar `init_point` ali levava para
    o checkout de produção. E `redirect(None)` levantava exceção quando o MP
    respondia 201 sem o campo.
    """
    if settings.MERCADOPAGO_USE_SANDBOX:
        return recurso.get("sandbox_init_point") or recurso.get("init_point")
    return recurso.get("init_point")


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
    """
    Inicia o checkout no Mercado Pago.

    Só aceita POST. Como GET, criava preapproval no MP e Subscription no banco
    como efeito colateral de uma navegação: qualquer prefetch de link (WhatsApp,
    Slack, o próprio browser) gerava assinatura pendente, e um link em site de
    terceiro fazia o usuário logado criar uma assinatura sem intenção nenhuma
    (navegação top-level passa com SameSite=Lax).
    """

    def post(self, request: HttpRequest, plan: str) -> HttpResponse:
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
        # uuid4 e nao timestamp: em segundos, dois cliques no mesmo segundo geravam
        # a mesma referencia, e o webhook casava com a assinatura errada.
        external_reference = f"user:{request.user.id}|plan:{plan_key}|ref:{uuid.uuid4().hex[:12]}"

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
                # O RuntimeError do serviço carrega o corpo da resposta do MP,
                # com ids internos e mensagens em inglês. Isso vai para o log,
                # não para a tela do cliente.
                logger.exception("[payments] Falha ao criar preferência: %s", exc)
                messages.error(
                    request,
                    "Não foi possível iniciar o pagamento agora. "
                    "Tente novamente em alguns minutos.",
                )
                return redirect(reverse("payments:plans"))

            destino = _link_de_checkout(preference)
            if not destino:
                logger.error("[payments] Preferência criada sem init_point: %s", preference)
                messages.error(
                    request,
                    "Não foi possível iniciar o pagamento agora. "
                    "Tente novamente em alguns minutos.",
                )
                return redirect(reverse("payments:plans"))
            return redirect(destino)

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
            logger.exception("[payments] Falha ao criar assinatura: %s", exc)
            messages.error(
                request,
                "Não foi possível iniciar a assinatura agora. Tente novamente em alguns minutos.",
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

        destino = _link_de_checkout(preapproval)
        if not destino:
            logger.error("[payments] Preapproval criada sem init_point: %s", preapproval)
            messages.error(
                request,
                "Não foi possível iniciar a assinatura agora. Tente novamente em alguns minutos.",
            )
            return redirect(reverse("payments:plans"))
        return redirect(destino)


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

    O roteamento por tipo é explícito e nunca adivinha. Antes, tudo que não
    fosse exatamente `preapproval` caía no fluxo de pagamento: um
    `subscription_preapproval` (o formato atual para eventos de assinatura)
    virava `fetch_payment(<id de preapproval>)`, respondia 404 e sumia sem
    deixar rastro. Cancelamento, pausa e expiração de assinatura nunca chegavam
    ao banco — o acesso só era cortado quando a data vencia.
    """

    # Eventos de assinatura. O MP usa os dois nomes conforme a versão da
    # integração que criou a notificação.
    TOPICOS_ASSINATURA = {"preapproval", "subscription_preapproval"}

    # Pagamento avulso ou cobrança de cartão.
    TOPICOS_PAGAMENTO = {"payment"}

    # Cobrança recorrente de uma assinatura. Vive em /authorized_payments/{id},
    # não em /v1/payments/{id}.
    TOPICOS_PAGAMENTO_ASSINATURA = {"subscription_authorized_payment"}

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

        if not data_id:
            logger.info("[payments] Webhook sem id de recurso (topic=%r); ignorado.", topic)
            return HttpResponse(status=200)

        if topic in self.TOPICOS_ASSINATURA:
            return self._tratar_assinatura(data_id)

        if topic in self.TOPICOS_PAGAMENTO:
            return self._tratar_pagamento(data_id)

        if topic in self.TOPICOS_PAGAMENTO_ASSINATURA:
            return self._tratar_pagamento_de_assinatura(data_id)

        # Nada de adivinhar: um id de preapproval consultado como pagamento dá
        # 404 e o evento se perde em silêncio. Respondemos 200 (não adianta o MP
        # reenviar algo que não sabemos tratar) e registramos o suficiente para
        # mapear o formato depois.
        logger.warning(
            "[payments] Webhook com topic não tratado: %r (id=%s). Payload: %s",
            topic,
            data_id,
            json.dumps(payload)[:500],
        )
        return HttpResponse(status=200)

    # -- fluxos -------------------------------------------------------------

    def _tratar_assinatura(self, preapproval_id: str) -> HttpResponse:
        try:
            dados = fetch_preapproval(preapproval_id)
        except Exception as exc:
            return self._falha_na_consulta("preapproval", preapproval_id, exc)

        dados.setdefault("id", preapproval_id)
        resultado = apply_preapproval_event(dados)
        logger.info("[payments] Webhook: preapproval %s -> %s", preapproval_id, resultado)
        return HttpResponse(status=200)

    def _tratar_pagamento(self, payment_id: str) -> HttpResponse:
        try:
            dados = fetch_payment(payment_id)
        except Exception as exc:
            return self._falha_na_consulta("payment", payment_id, exc)

        dados.setdefault("id", payment_id)
        resultado = apply_payment_event(dados)
        logger.info("[payments] Webhook: payment %s -> %s", payment_id, resultado)
        return HttpResponse(status=200)

    def _tratar_pagamento_de_assinatura(self, authorized_payment_id: str) -> HttpResponse:
        """
        Cobrança recorrente de uma assinatura.

        O recurso traz o `payment` real dentro dele; é esse que carrega status e
        metadata. Sem o payment embutido, não há o que aplicar — respondemos 200
        e registramos, porque reenviar não mudaria nada.
        """
        try:
            dados = fetch_authorized_payment(authorized_payment_id)
        except Exception as exc:
            return self._falha_na_consulta("authorized_payment", authorized_payment_id, exc)

        pagamento = dados.get("payment") or {}
        payment_id = pagamento.get("id")
        if not payment_id:
            logger.warning(
                "[payments] authorized_payment %s sem payment embutido; ignorado.",
                authorized_payment_id,
            )
            return HttpResponse(status=200)

        # O recurso embutido é resumido (status e id). Buscamos o pagamento
        # completo, que é onde estão o metadata e o valor.
        try:
            dados_pagamento = fetch_payment(str(payment_id))
        except Exception as exc:
            return self._falha_na_consulta("payment", str(payment_id), exc)

        dados_pagamento.setdefault("id", str(payment_id))
        resultado = apply_payment_event(dados_pagamento)
        logger.info(
            "[payments] Webhook: authorized_payment %s -> payment %s -> %s",
            authorized_payment_id,
            payment_id,
            resultado,
        )
        return HttpResponse(status=200)

    def _falha_na_consulta(self, recurso: str, identificador: str, exc: Exception) -> HttpResponse:
        logger.exception(
            "[payments] Erro ao buscar %s %s no webhook: %s", recurso, identificador, exc
        )
        if _erro_e_transitorio(exc):
            # 503 faz o Mercado Pago reenviar com backoff. Responder 200 aqui
            # descartava o evento e o plano nunca era liberado.
            return HttpResponse(status=503)
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
