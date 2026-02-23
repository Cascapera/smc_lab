"""
Testes do app payments - MercadoPago, webhook, views.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.tests import create_user

from .models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from .services.mercadopago import extract_payment_id, validate_webhook_signature

# ---------------------------------------------------------------------------
# Services - extract_payment_id
# ---------------------------------------------------------------------------


class ExtractPaymentIdTest(TestCase):
    """Testes de extract_payment_id."""

    def test_extrai_de_query_params_data_id(self):
        result = extract_payment_id({"data.id": "12345"}, {})
        self.assertEqual(result, "12345")

    def test_extrai_de_query_params_id(self):
        result = extract_payment_id({"id": "67890"}, {})
        self.assertEqual(result, "67890")

    def test_extrai_de_payload_data_id(self):
        result = extract_payment_id({}, {"data": {"id": "99999"}})
        self.assertEqual(result, "99999")

    def test_retorna_none_quando_ausente(self):
        self.assertIsNone(extract_payment_id({}, {}))
        self.assertIsNone(extract_payment_id({}, {"data": {}}))


# ---------------------------------------------------------------------------
# Services - validate_webhook_signature
# ---------------------------------------------------------------------------


class ValidateWebhookSignatureTest(TestCase):
    """Testes de validate_webhook_signature."""

    def test_retorna_true_quando_secret_vazio(self):
        self.assertTrue(validate_webhook_signature("ts=1,v1=abc", None, "123", ""))

    def test_retorna_false_quando_x_signature_ausente(self):
        self.assertFalse(validate_webhook_signature(None, None, "123", "my_secret"))

    def test_retorna_false_quando_data_id_ausente(self):
        self.assertFalse(validate_webhook_signature("ts=1,v1=abc", None, None, "my_secret"))

    def test_valida_assinatura_correta(self):
        secret = "test_secret"
        ts = "1704908010"
        data_id = "12345"
        manifest = f"id:{data_id};ts:{ts};"
        expected_hash = hmac.new(
            secret.encode(),
            manifest.encode(),
            hashlib.sha256,
        ).hexdigest()
        x_signature = f"ts={ts},v1={expected_hash}"

        self.assertTrue(validate_webhook_signature(x_signature, None, data_id, secret))

    def test_rejeita_assinatura_invalida(self):
        x_signature = "ts=1704908010,v1=invalid_hash"
        self.assertFalse(validate_webhook_signature(x_signature, None, "12345", "my_secret"))


# ---------------------------------------------------------------------------
# Views - PlanListView
# ---------------------------------------------------------------------------


class PlanListViewTest(TestCase):
    """Testes da PlanListView."""

    def test_retorna_200_com_plans_no_contexto(self):
        response = self.client.get(reverse("payments:plans"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("plans", response.context)
        self.assertIn("currency", response.context)


# ---------------------------------------------------------------------------
# Views - CreateCheckoutView
# ---------------------------------------------------------------------------


class CreateCheckoutViewTest(TestCase):
    """Testes da CreateCheckoutView."""

    def setUp(self):
        self.user = create_user()

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("payments:checkout", kwargs={"plan": "basic_monthly"}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_plano_invalido_redireciona_para_plans(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("payments:checkout", kwargs={"plan": "plano_inexistente"})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("payments:plans"))

    @patch("payments.views.create_preapproval")
    @patch("payments.views.settings")
    def test_checkout_assinatura_redireciona_para_mercado_pago(
        self, mock_settings, mock_create_preapproval
    ):
        mock_create_preapproval.return_value = {
            "id": "preapproval_123",
            "init_point": "https://www.mercadopago.com.br/checkout/123",
        }
        mock_settings.MERCADOPAGO_BACK_URL = "https://ngrok.io/retorno"
        mock_settings.MERCADOPAGO_WEBHOOK_URL = "https://ngrok.io/webhook"
        mock_settings.MERCADOPAGO_ACCESS_TOKEN = "token"
        mock_settings.MERCADOPAGO_USE_SANDBOX = False
        mock_settings.MERCADOPAGO_TEST_PAYER_EMAIL = ""
        mock_settings.MERCADOPAGO_PLANS = {
            "basic_monthly": {
                "plan": "basic",
                "label": "Basic Mensal",
                "amount": Decimal("79.90"),
                "frequency": 1,
                "frequency_type": "months",
                "billing_type": "subscription",
            }
        }
        mock_settings.MERCADOPAGO_CURRENCY = "BRL"
        mock_settings.MERCADOPAGO_TRIAL_DAYS = 0

        self.client.force_login(self.user)
        response = self.client.get(reverse("payments:checkout", kwargs={"plan": "basic_monthly"}))

        self.assertEqual(response.status_code, 302)
        self.assertIn("mercadopago.com", response.url)
        self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)


# ---------------------------------------------------------------------------
# Views - MercadoPagoWebhookView
# ---------------------------------------------------------------------------


class MercadoPagoWebhookViewTest(TestCase):
    """Testes da MercadoPagoWebhookView."""

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def test_post_sem_payload_retorna_200(self):
        response = self.client.post(
            reverse("payments:webhook"),
            content_type="application/json",
            data="{}",
        )
        self.assertEqual(response.status_code, 200)

    @patch("payments.views.settings")
    @patch("payments.views.fetch_preapproval")
    def test_webhook_rejeita_assinatura_invalida_quando_secret_configurado(
        self, mock_fetch, mock_settings
    ):
        mock_settings.MERCADOPAGO_WEBHOOK_SECRET = "my_secret"
        payload = {
            "type": "preapproval",
            "data": {"id": "preapproval_123"},
        }
        response = self.client.post(
            reverse("payments:webhook"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_SIGNATURE="ts=1,v1=invalid_hash",
        )
        self.assertEqual(response.status_code, 401)
        mock_fetch.assert_not_called()

    @patch("payments.views.settings")
    @patch("payments.views.fetch_preapproval")
    def test_webhook_aceita_quando_secret_vazio(self, mock_fetch, mock_settings):
        mock_settings.MERCADOPAGO_WEBHOOK_SECRET = ""
        mock_fetch.return_value = {
            "id": "preapproval_123",
            "status": "authorized",
            "external_reference": "user:1|plan:basic_monthly|ts:1",
            "metadata": {
                "user_id": self.user.id,
                "plan_key": "basic_monthly",
                "plan": "basic",
            },
        }
        Subscription.objects.create(
            user=self.user,
            plan="basic",
            plan_key="basic_monthly",
            amount=Decimal("79.90"),
            status=SubscriptionStatus.PENDING,
            mp_preapproval_id="preapproval_123",
            external_reference="user:1|plan:basic_monthly|ts:1",
        )
        payload = {
            "type": "preapproval",
            "data": {"id": "preapproval_123"},
        }
        response = self.client.post(
            reverse("payments:webhook"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        mock_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PaymentModelTest(TestCase):
    """Testes do modelo Payment."""

    def setUp(self):
        self.user = create_user()

    def test_str_retorna_user_plan_status(self):
        payment = Payment.objects.create(
            user=self.user,
            plan="basic",
            amount=Decimal("79.90"),
            status=PaymentStatus.APPROVED,
        )
        self.assertIn(str(self.user), str(payment))
        self.assertIn("basic", str(payment))
        self.assertIn("approved", str(payment))


class SubscriptionModelTest(TestCase):
    """Testes do modelo Subscription."""

    def setUp(self):
        self.user = create_user()

    def test_str_retorna_user_plan_key_status(self):
        sub = Subscription.objects.create(
            user=self.user,
            plan="basic",
            plan_key="basic_monthly",
            amount=Decimal("79.90"),
            status=SubscriptionStatus.AUTHORIZED,
        )
        self.assertIn(str(self.user), str(sub))
        self.assertIn("basic_monthly", str(sub))
        self.assertIn("authorized", str(sub))
