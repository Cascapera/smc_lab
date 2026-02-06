from __future__ import annotations

import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from accounts.models import Profile
from .models import PaymentStatus, Subscription, SubscriptionStatus
from .services.mercadopago import (
    create_preapproval,
    create_preapproval_plan,
    create_preference,
    extract_payment_id,
    fetch_payment,
    fetch_preapproval,
)


class PlanListView(LoginRequiredMixin, TemplateView):
    template_name = "payments/plans.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["plans"] = settings.MERCADOPAGO_PLANS
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

        if not settings.MERCADOPAGO_ACCESS_TOKEN:
            messages.error(request, "Token do Mercado Pago não configurado.")
            return redirect(reverse("payments:plans"))

        config = settings.MERCADOPAGO_PLANS[plan_key]
        plan_name = config["plan"]
        amount = config["amount"]
        currency = settings.MERCADOPAGO_CURRENCY
        frequency = config["frequency"]
        frequency_type = config["frequency_type"]

        success_url = request.build_absolute_uri(reverse("payments:return"))
        failure_url = request.build_absolute_uri(reverse("payments:return"))
        pending_url = request.build_absolute_uri(reverse("payments:return"))
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


class PaymentReturnView(LoginRequiredMixin, TemplateView):
    template_name = "payments/return.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get("status") or "pending"
        preapproval_id = self.request.GET.get("preapproval_id") or self.request.GET.get("id")
        fallback_subscription = None
        if not preapproval_id:
            fallback_subscription = (
                Subscription.objects.filter(user=self.request.user)
                .exclude(mp_preapproval_id="")
                .order_by("-created_at")
                .first()
            )
            if fallback_subscription:
                preapproval_id = fallback_subscription.mp_preapproval_id
        if preapproval_id:
            try:
                preapproval = fetch_preapproval(preapproval_id)
                status = preapproval.get("status", status)
                subscription = Subscription.objects.filter(mp_preapproval_id=preapproval_id).first()
                if not subscription and fallback_subscription:
                    subscription = fallback_subscription
                if not subscription:
                    external_reference = preapproval.get("external_reference", "")
                    if external_reference:
                        subscription = Subscription.objects.filter(
                            external_reference=external_reference
                        ).first()
                if subscription:
                    subscription.status = status
                    subscription.raw_payload = preapproval
                    subscription.save(update_fields=["status", "raw_payload", "updated_at"])
                    if status == SubscriptionStatus.AUTHORIZED:
                        _apply_plan(subscription.user.profile, subscription.plan_key, subscription.plan)
                    elif status in {
                        SubscriptionStatus.CANCELLED,
                        SubscriptionStatus.PAUSED,
                        SubscriptionStatus.EXPIRED,
                    }:
                        _schedule_plan_end(
                            subscription.user.profile,
                            preapproval,
                            subscription.plan,
                        )
            except Exception:
                pass

        payment_id = extract_payment_id(self.request.GET, {})
        if payment_id:
            try:
                payment = fetch_payment(payment_id)
                payment_status = payment.get("status") or status
                metadata = payment.get("metadata") or {}
                user_id = metadata.get("user_id")
                plan_key = metadata.get("plan_key")
                plan = metadata.get("plan")
                if (
                    payment_status == PaymentStatus.APPROVED
                    and user_id
                    and plan_key
                    and plan
                ):
                    profile = Profile.objects.filter(user_id=user_id).first()
                    if profile:
                        _apply_plan(profile, plan_key, plan)
                elif payment_status in {PaymentStatus.CHARGEDBACK, PaymentStatus.REFUNDED}:
                    profile = Profile.objects.filter(user_id=user_id).first() if user_id else None
                    if profile:
                        _maybe_revoke_plan(profile)
            except Exception:
                pass

        context["status"] = status
        return context


@method_decorator(csrf_exempt, name="dispatch")
class MercadoPagoWebhookView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except json.JSONDecodeError:
            payload = {}

        topic = payload.get("type") or payload.get("topic") or request.GET.get("topic")
        if topic == "preapproval":
            preapproval_id = extract_payment_id(request.GET, payload)
            if not preapproval_id:
                return HttpResponse(status=200)

            try:
                preapproval_data = fetch_preapproval(preapproval_id)
            except Exception:
                return HttpResponse(status=200)

            status = preapproval_data.get("status", SubscriptionStatus.PENDING)
            external_reference = preapproval_data.get("external_reference", "")
            metadata = preapproval_data.get("metadata") or {}
            user_id = metadata.get("user_id")
            plan_key = metadata.get("plan_key")
            plan = metadata.get("plan")

            subscription = Subscription.objects.filter(mp_preapproval_id=preapproval_id).first()
            if not subscription and external_reference:
                subscription = Subscription.objects.filter(external_reference=external_reference).first()
            if not subscription and user_id and plan_key and plan:
                subscription = Subscription.objects.create(
                    user_id=user_id,
                    plan=plan,
                    plan_key=plan_key,
                    amount=preapproval_data.get("auto_recurring", {}).get("transaction_amount") or 0,
                    currency=preapproval_data.get("auto_recurring", {}).get("currency_id")
                    or settings.MERCADOPAGO_CURRENCY,
                )

            if subscription:
                subscription.mp_preapproval_id = preapproval_id
                subscription.status = status
                subscription.raw_payload = preapproval_data
                subscription.save(update_fields=["mp_preapproval_id", "status", "raw_payload", "updated_at"])

                if status == SubscriptionStatus.AUTHORIZED:
                    _apply_plan(subscription.user.profile, subscription.plan_key, subscription.plan)
                elif status in {
                    SubscriptionStatus.CANCELLED,
                    SubscriptionStatus.PAUSED,
                    SubscriptionStatus.EXPIRED,
                }:
                    _schedule_plan_end(
                        subscription.user.profile,
                        preapproval_data,
                        subscription.plan,
                    )

            return HttpResponse(status=200)

        payment_id = extract_payment_id(request.GET, payload)
        if not payment_id:
            return HttpResponse(status=200)

        try:
            payment_data = fetch_payment(payment_id)
        except Exception:
            return HttpResponse(status=200)

        status = payment_data.get("status", PaymentStatus.PENDING)
        status_detail = payment_data.get("status_detail", "")
        external_reference = payment_data.get("external_reference", "")
        metadata = payment_data.get("metadata") or {}
        user_id = metadata.get("user_id")
        plan_key = metadata.get("plan_key")
        plan = metadata.get("plan")

        subscription = None
        if user_id and plan_key and plan:
            subscription = Subscription.objects.filter(
                user_id=user_id, plan_key=plan_key
            ).first()

        if status == PaymentStatus.APPROVED and subscription:
            _apply_plan(subscription.user.profile, subscription.plan_key, subscription.plan)
        elif status in {PaymentStatus.CHARGEDBACK, PaymentStatus.REFUNDED} and subscription:
            _maybe_revoke_plan(subscription.user.profile)

        return HttpResponse(status=200)


def _apply_plan(profile: Profile, plan_key: str, plan: str) -> None:
    now = timezone.now()
    start_at = (
        profile.plan_expires_at
        if profile.plan == plan and profile.plan_expires_at and profile.plan_expires_at > now
        else now
    )

    profile.plan = plan
    profile.plan_expires_at = start_at + timedelta(days=_get_plan_duration(plan_key))
    profile.save(update_fields=["plan", "plan_expires_at"])
    try:
        from discord_integration.tasks import sync_user_roles

        sync_user_roles.delay(profile.user_id)
    except Exception:
        pass


def _get_plan_duration(plan_key: str) -> int:
    plan = settings.MERCADOPAGO_PLANS.get(plan_key, {})
    return int(plan.get("duration_days", 30))


def _maybe_revoke_plan(profile: Profile) -> None:
    active = Subscription.objects.filter(
        user=profile.user,
        status=SubscriptionStatus.AUTHORIZED,
    ).exists()
    if active:
        return

    profile.plan = "free"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])
    try:
        from discord_integration.tasks import sync_user_roles

        sync_user_roles.delay(profile.user_id)
    except Exception:
        pass


def _schedule_plan_end(
    profile: Profile, preapproval_data: dict[str, object], plan: str | None = None
) -> None:
    next_payment_date = preapproval_data.get("next_payment_date")
    if not next_payment_date:
        auto_recurring = preapproval_data.get("auto_recurring") or {}
        next_payment_date = (
            auto_recurring.get("next_payment_date") or auto_recurring.get("end_date")
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

    _maybe_revoke_plan(profile)


def _parse_mp_datetime(value: object | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed and timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    return None


def _ensure_preapproval_plan(
    plan_key: str, config: dict, currency: str, back_url: str
) -> str:
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
