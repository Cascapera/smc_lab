from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class PagarmeConfig:
    secret_key: str
    base_url: str
    webhook_secret: str


def get_config() -> PagarmeConfig:
    return PagarmeConfig(
        secret_key=settings.PAGARME_SECRET_KEY,
        base_url=settings.PAGARME_BASE_URL,
        webhook_secret=settings.PAGARME_WEBHOOK_SECRET,
    )


def _auth(config: PagarmeConfig) -> tuple[str, str]:
    return (config.secret_key, "")


def create_payment_link(payload: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    if not config.secret_key:
        raise RuntimeError("PAGARME_SECRET_KEY não configurado.")

    resp = requests.post(
        f"{config.base_url}/paymentlinks",
        json=payload,
        auth=_auth(config),
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Erro Pagar.me (paymentlink): {resp.text}")
    return resp.json()


def fetch_order(order_id: str) -> dict[str, Any]:
    config = get_config()
    if not config.secret_key:
        raise RuntimeError("PAGARME_SECRET_KEY não configurado.")

    resp = requests.get(
        f"{config.base_url}/orders/{order_id}",
        auth=_auth(config),
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Erro Pagar.me (order): {resp.text}")
    return resp.json()


def verify_webhook_signature(
    payload_body: bytes, signature_header: str | None, webhook_secret: str
) -> bool:
    if not webhook_secret:
        return True
    if not signature_header:
        return False

    expected = hmac.new(webhook_secret.encode("utf-8"), payload_body, sha256).hexdigest()
    signature = signature_header.replace("sha256=", "").strip()
    return hmac.compare_digest(expected, signature)


def parse_webhook_payload(raw_body: bytes) -> dict[str, Any]:
    try:
        return json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError:
        logger.warning("[pagarme] Webhook com JSON invalido.")
        return {}
