"""
Template tags do app trades.
"""

import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Títulos que a IA, regras fixas e livros usam na resposta (destacar em negrito)
ANALYTICS_LABELS = (
    "Regra:",
    "Ponto forte:",
    "Ponto fraco:",
    "Próximo passo:",
    "Captura do ganho técnico:",
    "Sobre seu win rate:",
    "Para melhorar suas operações recomendo que você estude os seguintes pontos:",
    "No Livro Smart Money Concept estude os capítulos",
    "No Livro The Black Book of Smart Money estude os capítulos",
    "Caso ainda não tenha os livros você poderá comprar nos links abaixo:",
)


@register.filter
def format_analytics_result(value: str) -> str:
    """
    Formata o texto da resposta da IA: deixa os títulos (Regra:, Ponto forte:, etc.) em negrito.
    Mantém quebras de linha (pre-wrap no CSS).
    """
    if not value or not isinstance(value, str):
        return value
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for label in ANALYTICS_LABELS:
        # Linha que começa com o título (opcional espaços no início)
        pattern = re.compile(r"^(\s*)" + re.escape(label) + r"(\s*)(.*)$", re.MULTILINE)
        escaped = pattern.sub(
            r'\1<strong style="color:#38bdf8;">' + label + r"</strong>\2\3", escaped
        )
    return mark_safe(escaped)
