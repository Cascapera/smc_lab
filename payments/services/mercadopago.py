from __future__ import annotations

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
