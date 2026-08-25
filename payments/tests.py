"""
Testes do app payments - MercadoPago, webhook, views.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import requests
from django.db.utils import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests import create_user

from .models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from .services import plans
from .services.mercadopago import extract_payment_id, validate_webhook_signature
from .services.plans import apply_payment_event, apply_preapproval_event

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


# ---------------------------------------------------------------------------
# Idempotência da aplicação de plano (P1 e P2)
# ---------------------------------------------------------------------------


def _payment_payload(
    user, *, payment_id="pay_1", status="approved", plan_key="basic_monthly", amount=79.90
):
    return {
        "id": payment_id,
        "status": status,
        "transaction_amount": amount,
        "currency_id": "BRL",
        "external_reference": f"user:{user.id}|plan:{plan_key}|ts:1",
        "metadata": {"user_id": user.id, "plan_key": plan_key, "plan": "basic"},
    }


def _preapproval_payload(user, *, preapproval_id="pre_1", status="authorized"):
    return {
        "id": preapproval_id,
        "status": status,
        "external_reference": f"user:{user.id}|plan:basic_monthly|ts:1",
        "metadata": {"user_id": user.id, "plan_key": "basic_monthly", "plan": "basic"},
        "auto_recurring": {"transaction_amount": 79.90, "currency_id": "BRL"},
    }


class ApplyPaymentEventTest(TestCase):
    """
    Regressão do bug de idempotência.

    O Mercado Pago reenvia a mesma notificação várias vezes até receber 200.
    Antes, cada entrega somava outro período: um pagamento anual entregue 3x
    virava 3 anos de plano.
    """

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def test_pagamento_aprovado_aplica_plano(self):
        result = apply_payment_event(_payment_payload(self.user))
        self.profile.refresh_from_db()
        self.assertEqual(result, plans.APPLIED)
        self.assertEqual(self.profile.plan, "basic")
        self.assertIsNotNone(self.profile.plan_expires_at)

    def test_pagamento_aprovado_grava_registro_de_pagamento(self):
        """Sem o Payment gravado não há trilha de auditoria nem idempotência."""
        apply_payment_event(_payment_payload(self.user, payment_id="pay_abc"))
        payment = Payment.objects.get(mp_payment_id="pay_abc")
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.status, PaymentStatus.APPROVED)
        self.assertEqual(payment.amount, Decimal("79.90"))

    def test_reentrega_do_mesmo_pagamento_nao_estende_plano(self):
        payload = _payment_payload(self.user)
        apply_payment_event(payload)
        self.profile.refresh_from_db()
        expira_apos_primeira = self.profile.plan_expires_at

        for _ in range(4):
            result = apply_payment_event(payload)
            self.assertEqual(result, plans.ALREADY_PROCESSED)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, expira_apos_primeira)
        self.assertEqual(Payment.objects.filter(mp_payment_id="pay_1").count(), 1)

    def test_pagamentos_diferentes_estendem_o_plano(self):
        """Renovação real (outro payment_id) deve somar período."""
        apply_payment_event(_payment_payload(self.user, payment_id="pay_1"))
        self.profile.refresh_from_db()
        primeira = self.profile.plan_expires_at

        apply_payment_event(_payment_payload(self.user, payment_id="pay_2"))
        self.profile.refresh_from_db()
        self.assertGreater(self.profile.plan_expires_at, primeira)

    def test_pagamento_de_outro_usuario_e_ignorado(self):
        """
        Regressão do IDOR: a página de retorno aplicava o plano no `user_id` do
        pagamento, não no usuário logado. Com um payment_id alheio dava para
        estender (ou revogar) o plano de terceiros.
        """
        outro = create_user(email="outro@test.com")
        payload = _payment_payload(self.user)

        result = apply_payment_event(payload, restrict_to_user_id=outro.id)

        self.assertEqual(result, plans.IGNORED_NOT_OWNER)
        self.profile.refresh_from_db()
        outro.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "free")
        self.assertEqual(outro.profile.plan, "free")
        self.assertFalse(Payment.objects.exists())

    def test_proprio_usuario_pode_processar_seu_pagamento(self):
        result = apply_payment_event(_payment_payload(self.user), restrict_to_user_id=self.user.id)
        self.assertEqual(result, plans.APPLIED)

    def test_chargeback_revoga_plano(self):
        apply_payment_event(_payment_payload(self.user))
        result = apply_payment_event(
            _payment_payload(self.user, payment_id="pay_cb", status="chargeback")
        )
        self.profile.refresh_from_db()
        self.assertEqual(result, plans.REVOKED)
        self.assertEqual(self.profile.plan, "free")
        self.assertIsNone(self.profile.plan_expires_at)

    def test_chargeback_reentregue_nao_reprocessa(self):
        payload = _payment_payload(self.user, payment_id="pay_cb", status="chargeback")
        apply_payment_event(payload)
        result = apply_payment_event(payload)
        self.assertEqual(result, plans.ALREADY_PROCESSED)

    def test_pagamento_sem_id_e_ignorado(self):
        payload = _payment_payload(self.user)
        payload["id"] = ""
        self.assertEqual(apply_payment_event(payload), plans.IGNORED_NO_ID)


class ApplyPreapprovalEventTest(TestCase):
    """Idempotência das assinaturas: `authorized` só libera plano na transição."""

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def test_authorized_aplica_plano(self):
        result = apply_preapproval_event(_preapproval_payload(self.user))
        self.profile.refresh_from_db()
        self.assertEqual(result, plans.APPLIED)
        self.assertEqual(self.profile.plan, "basic")

    def test_authorized_repetido_nao_estende_plano(self):
        payload = _preapproval_payload(self.user)
        apply_preapproval_event(payload)
        self.profile.refresh_from_db()
        expira = self.profile.plan_expires_at

        for _ in range(3):
            self.assertEqual(apply_preapproval_event(payload), plans.ALREADY_PROCESSED)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, expira)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_preapproval_de_outro_usuario_e_ignorado(self):
        outro = create_user(email="outro@test.com")
        result = apply_preapproval_event(
            _preapproval_payload(self.user), restrict_to_user_id=outro.id
        )
        self.assertEqual(result, plans.IGNORED_NOT_OWNER)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "free")

    def test_cancelamento_encerra_plano(self):
        apply_preapproval_event(_preapproval_payload(self.user))
        result = apply_preapproval_event(_preapproval_payload(self.user, status="cancelled"))
        self.assertEqual(result, plans.PLAN_ENDED)


class PaymentUniqueConstraintTest(TestCase):
    """A idempotência depende da constraint no banco, não só do código."""

    def setUp(self):
        self.user = create_user()

    def test_nao_permite_dois_pagamentos_com_mesmo_mp_payment_id(self):
        Payment.objects.create(user=self.user, plan="basic", mp_payment_id="dup_1")
        with self.assertRaises(IntegrityError):
            Payment.objects.create(user=self.user, plan="basic", mp_payment_id="dup_1")

    def test_permite_varios_pagamentos_sem_mp_payment_id(self):
        Payment.objects.create(user=self.user, plan="basic", mp_payment_id="")
        Payment.objects.create(user=self.user, plan="basic", mp_payment_id="")
        self.assertEqual(Payment.objects.filter(mp_payment_id="").count(), 2)


# ---------------------------------------------------------------------------
# Views - idempotência ponta a ponta (HTTP)
# ---------------------------------------------------------------------------


@override_settings(MERCADOPAGO_WEBHOOK_SECRET="")
class PaymentReturnViewIdempotencyTest(TestCase):
    """
    Regressão do bug mais grave desta fase.

    A página de retorno aplicava o plano a cada `get_context_data`, então dar F5
    somava outro período toda vez: um assinante Basic com o plano vigente que
    recarregasse a página 12 vezes ganhava 360 dias sem pagar nada.
    """

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile
        self.client.force_login(self.user)
        self.url = reverse("payments:return")

    @patch("payments.views.fetch_preapproval")
    def test_f5_na_pagina_de_retorno_nao_estende_plano(self, mock_fetch_preapproval):
        mock_fetch_preapproval.return_value = {
            "id": "pre_1",
            "status": "authorized",
            "external_reference": f"user:{self.user.id}|plan:basic_monthly|ts:1",
            "metadata": {
                "user_id": self.user.id,
                "plan_key": "basic_monthly",
                "plan": "basic",
            },
            "auto_recurring": {"transaction_amount": 79.90, "currency_id": "BRL"},
        }

        response = self.client.get(self.url, {"preapproval_id": "pre_1"})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "basic")
        expira_apos_primeira = self.profile.plan_expires_at

        for _ in range(11):
            self.client.get(self.url, {"preapproval_id": "pre_1"})

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, expira_apos_primeira)

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_f5_com_pagamento_avulso_nao_estende_plano(
        self, mock_fetch_preapproval, mock_fetch_payment
    ):
        # O MP responde 404 ao consultar um id de pagamento como preapproval.
        mock_fetch_preapproval.side_effect = Exception("404 preapproval não encontrado")
        mock_fetch_payment.return_value = {
            "id": "pay_1",
            "status": "approved",
            "transaction_amount": 589.50,
            "currency_id": "BRL",
            "metadata": {
                "user_id": self.user.id,
                "plan_key": "premium_annual",
                "plan": "premium",
            },
        }

        self.client.get(self.url, {"id": "pay_1"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "premium")
        expira_apos_primeira = self.profile.plan_expires_at

        for _ in range(5):
            self.client.get(self.url, {"id": "pay_1"})

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, expira_apos_primeira)
        self.assertEqual(Payment.objects.filter(mp_payment_id="pay_1").count(), 1)

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_nao_processa_pagamento_de_outro_usuario(
        self, mock_fetch_preapproval, mock_fetch_payment
    ):
        """
        Regressão do IDOR: o plano era aplicado no `user_id` que vinha no
        pagamento, não no usuário logado. Como os ids do MP são sequenciais,
        um usuário podia estender (ou revogar) o plano de outra pessoa.
        """
        vitima = create_user(email="vitima@test.com")
        mock_fetch_preapproval.side_effect = Exception("404")
        mock_fetch_payment.return_value = {
            "id": "pay_da_vitima",
            "status": "approved",
            "transaction_amount": 1800.00,
            "metadata": {
                "user_id": vitima.id,
                "plan_key": "premium_plus_annual",
                "plan": "premium_plus",
            },
        }

        response = self.client.get(self.url, {"id": "pay_da_vitima"})

        self.assertEqual(response.status_code, 200)
        vitima.profile.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(vitima.profile.plan, "free")
        self.assertEqual(self.profile.plan, "free")
        self.assertFalse(Payment.objects.exists())

    @patch("payments.views.fetch_preapproval")
    def test_nao_processa_assinatura_de_outro_usuario(self, mock_fetch_preapproval):
        vitima = create_user(email="vitima2@test.com")
        Subscription.objects.create(
            user=vitima,
            plan="premium",
            plan_key="premium_monthly",
            amount=Decimal("129.90"),
            status=SubscriptionStatus.PENDING,
            mp_preapproval_id="pre_da_vitima",
        )
        mock_fetch_preapproval.return_value = {
            "id": "pre_da_vitima",
            "status": "authorized",
            "metadata": {
                "user_id": vitima.id,
                "plan_key": "premium_monthly",
                "plan": "premium",
            },
        }

        self.client.get(self.url, {"preapproval_id": "pre_da_vitima"})

        vitima.profile.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(vitima.profile.plan, "free")
        self.assertEqual(self.profile.plan, "free")


@override_settings(MERCADOPAGO_WEBHOOK_SECRET="")
class WebhookIdempotencyTest(TestCase):
    """O Mercado Pago reenvia a mesma notificação até receber 200."""

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile
        self.url = reverse("payments:webhook")

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    @patch("payments.views.fetch_payment")
    def test_reentregas_do_webhook_nao_estendem_plano(self, mock_fetch_payment):
        mock_fetch_payment.return_value = {
            "id": "pay_webhook",
            "status": "approved",
            "transaction_amount": 589.50,
            "metadata": {
                "user_id": self.user.id,
                "plan_key": "premium_annual",
                "plan": "premium",
            },
        }
        payload = {"type": "payment", "data": {"id": "pay_webhook"}}

        self.assertEqual(self._post(payload).status_code, 200)
        self.profile.refresh_from_db()
        expira_apos_primeira = self.profile.plan_expires_at
        self.assertIsNotNone(expira_apos_primeira)

        for _ in range(3):
            self.assertEqual(self._post(payload).status_code, 200)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, expira_apos_primeira)
        self.assertEqual(Payment.objects.filter(mp_payment_id="pay_webhook").count(), 1)

    @patch("payments.views.fetch_preapproval")
    def test_reentregas_de_preapproval_nao_estendem_plano(self, mock_fetch_preapproval):
        mock_fetch_preapproval.return_value = {
            "id": "pre_webhook",
            "status": "authorized",
            "metadata": {
                "user_id": self.user.id,
                "plan_key": "basic_monthly",
                "plan": "basic",
            },
            "auto_recurring": {"transaction_amount": 79.90, "currency_id": "BRL"},
        }
        payload = {"type": "preapproval", "data": {"id": "pre_webhook"}}

        self._post(payload)
        self.profile.refresh_from_db()
        expira_apos_primeira = self.profile.plan_expires_at

        for _ in range(3):
            self._post(payload)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, expira_apos_primeira)
        self.assertEqual(Subscription.objects.filter(mp_preapproval_id="pre_webhook").count(), 1)


# ---------------------------------------------------------------------------
# Regra de ranking: evento de plano inferior não rebaixa plano superior (P3)
# ---------------------------------------------------------------------------


class RankingDePlanosTest(TestCase):
    """
    O perfil guarda um único par (plan, plan_expires_at), então qualquer evento
    sobrescrevia os dois.

    Cenário real: assinante com Basic mensal ativo compra Premium+ anual. Na
    cobrança mensal seguinte do Basic, o webhook rebaixava o perfil para `basic`
    e truncava a validade para 30 dias — o usuário perdia ~335 dias já pagos.
    """

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def _dar_plano(self, plano, dias):
        self.profile.plan = plano
        self.profile.plan_expires_at = timezone.now() + timedelta(days=dias)
        self.profile.save()

    def test_evento_inferior_nao_rebaixa_plano_vigente(self):
        self._dar_plano("premium_plus", dias=365)
        expira_antes = self.profile.plan_expires_at

        apply_payment_event(
            _payment_payload(self.user, payment_id="pay_basic", plan_key="basic_monthly")
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "premium_plus")
        self.assertEqual(self.profile.plan_expires_at, expira_antes)

    def test_evento_superior_faz_upgrade(self):
        self._dar_plano("basic", dias=20)
        payload = _payment_payload(self.user, payment_id="pay_pp", amount=1800.00)
        payload["metadata"]["plan"] = "premium_plus"
        payload["metadata"]["plan_key"] = "premium_plus_annual"

        apply_payment_event(payload)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "premium_plus")

    def test_mesmo_plano_acumula_periodo(self):
        self._dar_plano("basic", dias=10)
        expira_antes = self.profile.plan_expires_at

        apply_payment_event(_payment_payload(self.user, payment_id="pay_renov"))

        self.profile.refresh_from_db()
        self.assertGreater(self.profile.plan_expires_at, expira_antes)

    def test_evento_inferior_volta_a_valer_com_plano_expirado(self):
        """Se o plano superior já venceu, o pagamento do inferior deve valer."""
        self.profile.plan = "premium_plus"
        self.profile.plan_expires_at = timezone.now() - timedelta(days=1)
        self.profile.save()

        apply_payment_event(_payment_payload(self.user, payment_id="pay_basic2"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "basic")

    def test_estorno_de_plano_inferior_nao_zera_plano_superior(self):
        """
        Antes: chargeback de um Basic zerava o perfil de quem tinha Premium+,
        porque a revogação só olhava se existia Subscription AUTHORIZED — e
        compras anuais one-time não criam Subscription.
        """
        self._dar_plano("premium_plus", dias=300)

        apply_payment_event(
            _payment_payload(
                self.user, payment_id="pay_cb_basic", status="chargeback", plan_key="basic_monthly"
            )
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "premium_plus")
        self.assertIsNotNone(self.profile.plan_expires_at)

    def test_estorno_do_proprio_plano_revoga(self):
        self._dar_plano("basic", dias=20)

        apply_payment_event(_payment_payload(self.user, payment_id="pay_cb", status="chargeback"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "free")

    def test_cancelamento_de_assinatura_inferior_nao_altera_plano_superior(self):
        self._dar_plano("premium_plus", dias=300)
        expira_antes = self.profile.plan_expires_at
        Subscription.objects.create(
            user=self.user,
            plan="basic",
            plan_key="basic_monthly",
            amount=Decimal("79.90"),
            status=SubscriptionStatus.AUTHORIZED,
            mp_preapproval_id="pre_basic",
        )

        apply_preapproval_event(
            _preapproval_payload(self.user, preapproval_id="pre_basic", status="cancelled")
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "premium_plus")
        self.assertEqual(self.profile.plan_expires_at, expira_antes)


# ---------------------------------------------------------------------------
# Webhook não perde evento quando o Mercado Pago está instável (P5)
# ---------------------------------------------------------------------------


@override_settings(MERCADOPAGO_WEBHOOK_SECRET="")
class WebhookErroTransitorioTest(TestCase):
    """
    Falha ao consultar o MP respondia 200: o MP considera entregue e nunca
    reenvia, então o pagamento aprovado nunca liberava o plano. Instabilidade de
    um minuto virava suporte manual.
    """

    def setUp(self):
        self.user = create_user()
        self.url = reverse("payments:webhook")

    def _post(self):
        return self.client.post(
            self.url,
            data=json.dumps({"type": "payment", "data": {"id": "pay_x"}}),
            content_type="application/json",
        )

    def _http_error(self, status):
        resposta = requests.Response()
        resposta.status_code = status
        return requests.HTTPError(response=resposta)

    @patch("payments.views.fetch_payment")
    def test_timeout_pede_reenvio(self, mock_fetch):
        mock_fetch.side_effect = requests.Timeout("tempo esgotado")
        self.assertEqual(self._post().status_code, 503)

    @patch("payments.views.fetch_payment")
    def test_queda_de_conexao_pede_reenvio(self, mock_fetch):
        mock_fetch.side_effect = requests.ConnectionError("conexao recusada")
        self.assertEqual(self._post().status_code, 503)

    @patch("payments.views.fetch_payment")
    def test_erro_500_do_mp_pede_reenvio(self, mock_fetch):
        mock_fetch.side_effect = self._http_error(500)
        self.assertEqual(self._post().status_code, 503)

    @patch("payments.views.fetch_payment")
    def test_rate_limit_pede_reenvio(self, mock_fetch):
        mock_fetch.side_effect = self._http_error(429)
        self.assertEqual(self._post().status_code, 503)

    @patch("payments.views.fetch_payment")
    def test_404_nao_pede_reenvio(self, mock_fetch):
        """Id que não existe é permanente: reenviar só geraria ruído."""
        mock_fetch.side_effect = self._http_error(404)
        self.assertEqual(self._post().status_code, 200)

    @patch("payments.views.fetch_payment")
    def test_400_nao_pede_reenvio(self, mock_fetch):
        mock_fetch.side_effect = self._http_error(400)
        self.assertEqual(self._post().status_code, 200)


# ---------------------------------------------------------------------------
# Roteamento do webhook por tipo de evento (P4)
# ---------------------------------------------------------------------------


@override_settings(MERCADOPAGO_WEBHOOK_SECRET="")
class WebhookRoteamentoTest(TestCase):
    """
    Antes, tudo que não fosse exatamente `preapproval` caía no fluxo de
    pagamento. Um `subscription_preapproval` (formato atual para eventos de
    assinatura) virava `fetch_payment(<id de preapproval>)`, dava 404 e sumia:
    cancelamento, pausa e expiração nunca chegavam ao banco.
    """

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile
        self.url = reverse("payments:webhook")

    def _post(self, tipo, ident="rec_1"):
        return self.client.post(
            self.url,
            data=json.dumps({"type": tipo, "data": {"id": ident}}),
            content_type="application/json",
        )

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_preapproval_vai_para_o_fluxo_de_assinatura(self, mock_pre, mock_pay):
        mock_pre.return_value = _preapproval_payload(self.user, preapproval_id="rec_1")
        self.assertEqual(self._post("preapproval").status_code, 200)
        mock_pre.assert_called_once()
        mock_pay.assert_not_called()

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_subscription_preapproval_tambem_vai_para_assinatura(self, mock_pre, mock_pay):
        """Este era o caso que sumia silenciosamente."""
        mock_pre.return_value = _preapproval_payload(self.user, preapproval_id="rec_1")
        self.assertEqual(self._post("subscription_preapproval").status_code, 200)
        mock_pre.assert_called_once()
        mock_pay.assert_not_called()

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_cancelamento_via_subscription_preapproval_chega_ao_banco(self, mock_pre, mock_pay):
        Subscription.objects.create(
            user=self.user,
            plan="basic",
            plan_key="basic_monthly",
            amount=Decimal("79.90"),
            status=SubscriptionStatus.AUTHORIZED,
            mp_preapproval_id="rec_1",
        )
        mock_pre.return_value = _preapproval_payload(
            self.user, preapproval_id="rec_1", status="cancelled"
        )

        self._post("subscription_preapproval")

        assinatura = Subscription.objects.get(mp_preapproval_id="rec_1")
        self.assertEqual(assinatura.status, "cancelled")

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_payment_vai_para_o_fluxo_de_pagamento(self, mock_pre, mock_pay):
        mock_pay.return_value = _payment_payload(self.user, payment_id="rec_1")
        self.assertEqual(self._post("payment").status_code, 200)
        mock_pay.assert_called_once()
        mock_pre.assert_not_called()

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_authorized_payment")
    def test_subscription_authorized_payment_usa_endpoint_proprio(self, mock_auth, mock_pay):
        """
        O id de um authorized payment não existe em /v1/payments/{id}: consultar
        lá dava 404 e a cobrança recorrente sumia.
        """
        mock_auth.return_value = {"id": "rec_1", "payment": {"id": "pay_99"}}
        mock_pay.return_value = _payment_payload(self.user, payment_id="pay_99")

        self.assertEqual(self._post("subscription_authorized_payment").status_code, 200)

        mock_auth.assert_called_once_with("rec_1")
        mock_pay.assert_called_once_with("pay_99")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "basic")

    @patch("payments.views.fetch_authorized_payment")
    def test_authorized_payment_sem_pagamento_embutido(self, mock_auth):
        mock_auth.return_value = {"id": "rec_1"}
        self.assertEqual(self._post("subscription_authorized_payment").status_code, 200)

    @patch("payments.views.fetch_payment")
    @patch("payments.views.fetch_preapproval")
    def test_topic_desconhecido_nao_adivinha(self, mock_pre, mock_pay):
        """
        Adivinhar era o bug: um id de assinatura consultado como pagamento dava
        404 e o evento se perdia. Agora não consulta nada e registra.
        """
        self.assertEqual(self._post("formato_que_nao_conhecemos").status_code, 200)
        mock_pay.assert_not_called()
        mock_pre.assert_not_called()

    @patch("payments.views.fetch_payment")
    def test_evento_sem_id_e_ignorado(self, mock_pay):
        resposta = self.client.post(
            self.url, data=json.dumps({"type": "payment"}), content_type="application/json"
        )
        self.assertEqual(resposta.status_code, 200)
        mock_pay.assert_not_called()


class ExtractPaymentIdRetornoTest(TestCase):
    """
    A back_url do Mercado Pago devolve `payment_id`, `collection_id` e
    `preference_id`. Nenhum era reconhecido: a página de retorno só olhava
    `data.id` e `id`, então pagamento avulso dependia exclusivamente do webhook.
    """

    def test_reconhece_payment_id_do_retorno(self):
        self.assertEqual(extract_payment_id({"payment_id": "123"}, {}), "123")

    def test_reconhece_collection_id(self):
        self.assertEqual(extract_payment_id({"collection_id": "456"}, {}), "456")

    def test_reconhece_preapproval_id(self):
        self.assertEqual(extract_payment_id({"preapproval_id": "pre_1"}, {}), "pre_1")

    def test_ignora_collection_id_nulo(self):
        """O MP manda `collection_id=null` como string quando não houve pagamento."""
        self.assertIsNone(extract_payment_id({"collection_id": "null"}, {}))

    def test_data_id_tem_prioridade(self):
        self.assertEqual(
            extract_payment_id({"data.id": "999", "payment_id": "123"}, {}),
            "999",
        )


# ---------------------------------------------------------------------------
# Valor e moeda do pagamento (P9)
# ---------------------------------------------------------------------------


class ValorDoPagamentoTest(TestCase):
    """
    Qualquer pagamento aprovado na conta com `metadata.plan_key` liberava o
    plano correspondente, sem conferir valor. O plano oculto
    `premium_plus_test` custa R$ 5,00 e usa o mesmo caminho do
    `premium_plus_annual`, de R$ 1.800,00.
    """

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def _payload_premium_plus(self, amount):
        payload = _payment_payload(self.user, payment_id="pay_pp", amount=amount)
        payload["metadata"]["plan"] = "premium_plus"
        payload["metadata"]["plan_key"] = "premium_plus_annual"
        return payload

    def test_valor_menor_nao_libera_plano(self):
        resultado = apply_payment_event(self._payload_premium_plus(5.00))

        self.assertEqual(resultado, plans.IGNORED_VALOR_INVALIDO)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "free")

    def test_valor_correto_libera(self):
        resultado = apply_payment_event(self._payload_premium_plus(1800.00))
        self.assertEqual(resultado, plans.APPLIED)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "premium_plus")

    def test_tolera_diferenca_de_centavo(self):
        """Arredondamento na conversão para float do payload do MP."""
        resultado = apply_payment_event(self._payload_premium_plus(1799.995))
        self.assertEqual(resultado, plans.APPLIED)

    def test_moeda_diferente_nao_libera(self):
        payload = self._payload_premium_plus(1800.00)
        payload["currency_id"] = "USD"
        resultado = apply_payment_event(payload)
        self.assertEqual(resultado, plans.IGNORED_VALOR_INVALIDO)

    def test_plano_desconhecido_nao_libera(self):
        payload = _payment_payload(self.user, payment_id="pay_x")
        payload["metadata"]["plan_key"] = "plano_que_nao_existe"
        resultado = apply_payment_event(payload)
        self.assertEqual(resultado, plans.IGNORED_VALOR_INVALIDO)
