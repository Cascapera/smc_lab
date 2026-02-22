from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


@dataclass
class MercadoPagoConfig:
    access_token: str
    currency: str
    use_sandbox: bool


def get_config() -> MercadoPagoConfig:
    return MercadoPagoConfig(
        access_token=settings.MERCADOPAGO_ACCESS_TOKEN,
        currency=settings.MERCADOPAGO_CURRENCY,
        use_sandbox=settings.MERCADOPAGO_USE_SANDBOX,
    )


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def create_preference(payload: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    if not config.access_token:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    resp = requests.post(
        "https://api.mercadopago.com/checkout/preferences",
        json=payload,
        headers=_headers(config.access_token),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_payment(payment_id: str) -> dict[str, Any]:
    config = get_config()
    if not config.access_token:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    resp = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=_headers(config.access_token),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def create_preapproval_plan(payload: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    if not config.access_token:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    resp = requests.post(
        "https://api.mercadopago.com/preapproval_plan",
        json=payload,
        headers=_headers(config.access_token),
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Erro Mercado Pago (preapproval_plan): {resp.text}")
    return resp.json()


def create_preapproval(payload: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    if not config.access_token:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    resp = requests.post(
        "https://api.mercadopago.com/preapproval",
        json=payload,
        headers=_headers(config.access_token),
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Erro Mercado Pago (preapproval): {resp.text}")
    return resp.json()


def fetch_preapproval(preapproval_id: str) -> dict[str, Any]:
    config = get_config()
    if not config.access_token:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    resp = requests.get(
        f"https://api.mercadopago.com/preapproval/{preapproval_id}",
        headers=_headers(config.access_token),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def extract_payment_id(query_params: dict[str, Any], payload: dict[str, Any]) -> str | None:
    payment_id = query_params.get("data.id") or query_params.get("id")
    if payment_id:
        return str(payment_id)

    data = payload.get("data") or {}
    data_id = data.get("id")
    if data_id:
        return str(data_id)
    return None


def validate_webhook_signature(
    x_signature: str | None,
    x_request_id: str | None,
    data_id: str | None,
    secret: str,
) -> bool:
    """
    Valida a assinatura x-signature do webhook MercadoPago.
    Retorna True se a assinatura for válida ou se secret estiver vazio (skip).
    Documentação: https://www.mercadopago.com.br/developers/en/docs/your-integrations/notifications/webhooks
    """
    if not secret or not secret.strip():
        return True  # Skip validation quando secret não configurado (retrocompatível)

    if not x_signature or not data_id:
        return False

    parts = [p.strip() for p in x_signature.split(",")]
    ts = None
    received_hash = None
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key, value = key.strip(), value.strip()
            if key == "ts":
                ts = value
            elif key == "v1":
                received_hash = value

    if not ts or not received_hash:
        return False

    manifest_parts = [f"id:{str(data_id).lower() if data_id.isalnum() else data_id}"]
    if x_request_id:
        manifest_parts.append(f"request-id:{x_request_id}")
    manifest_parts.append(f"ts:{ts}")
    manifest = ";".join(manifest_parts) + ";"

    expected_hash = hmac.new(
        secret.encode(),
        manifest.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_hash, received_hash)
