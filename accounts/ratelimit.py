"""
Chave de rate limit baseada no IP real do cliente.

O `key="ip"` do django-ratelimit usa `REMOTE_ADDR`. Em produção o gunicorn só
escuta em 127.0.0.1:8000 e quem fala com ele é o nginx do host, então
`REMOTE_ADDR` é o IP do proxy — o mesmo para todo mundo. Na prática o limite de
5 POSTs/min de login era **global**: cinco tentativas de qualquer pessoa
bloqueavam o login de todos os usuários, e um atacante derrubava o acesso ao
site com cinco requisições.

O nginx envia `proxy_set_header X-Real-IP $remote_addr;` — o valor é escrito
pelo próprio nginx a partir da conexão TCP, não copiado de um header do cliente,
então não é falsificável por quem chega pela internet. Por isso lemos
`X-Real-IP` e não `X-Forwarded-For` (que é `$proxy_add_x_forwarded_for`, ou
seja, o header do cliente + o IP real; o começo da lista é texto de quem chamou).
"""

from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)

REAL_IP_META_KEY = "HTTP_X_REAL_IP"

# Se o header sumir (location do nginx sem o proxy_set_header), o rate limit
# volta a ser global e silencioso. Como o site continua respondendo 200, isso
# passaria despercebido — então avisamos, uma vez por processo para não inundar.
_aviso_emitido = False


def _avisar_uma_vez(mensagem: str, *args) -> None:
    global _aviso_emitido
    if _aviso_emitido:
        return
    _aviso_emitido = True
    logger.warning(mensagem, *args)


def real_client_ip(request) -> str:
    """IP do cliente segundo o proxy, com queda para `REMOTE_ADDR`."""
    remote_addr = request.META.get("REMOTE_ADDR", "")
    valor = (request.META.get(REAL_IP_META_KEY) or "").strip()

    if not valor:
        _avisar_uma_vez(
            "[ratelimit] X-Real-IP ausente; usando REMOTE_ADDR (%s). "
            "O rate limit passa a valer para todos os clientes juntos. "
            "Confira o proxy_set_header no location do nginx.",
            remote_addr,
        )
        return remote_addr

    try:
        ipaddress.ip_address(valor)
    except ValueError:
        _avisar_uma_vez("[ratelimit] X-Real-IP com valor inválido; usando REMOTE_ADDR.")
        return remote_addr

    return valor


def client_ip_key(group, request) -> str:
    """Assinatura esperada pelo django-ratelimit para `key` invocável."""
    return real_client_ip(request)
