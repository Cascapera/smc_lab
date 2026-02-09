"""
Serviço de chamada à OpenAI para a Análise por IA.
Usa GPT-4o mini por padrão (custo baixo, boa qualidade).
"""

from __future__ import annotations

import logging

from django.conf import settings

from .ai_prompts import SYSTEM_PROMPT, build_analytics_user_prompt

logger = logging.getLogger(__name__)


def run_analytics_llm(context: dict) -> str:
    """
    Chama a OpenAI com o contexto da análise e retorna a resposta em texto.
    context: dicionário com top3_best_combos, top3_worst_combos, advanced,
             improvement_reais, improvement_new_total, improvement_pct.
    Levanta OpenAIError ou retorna string vazia se API key não configurada.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key.strip():
        logger.warning("OPENAI_API_KEY não configurada; análise por IA não executada.")
        return ""

    model = getattr(settings, "OPENAI_ANALYTICS_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

    user_content = build_analytics_user_prompt(context)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1000,
            temperature=0.3,
        )
        choice = response.choices[0] if response.choices else None
        if choice and choice.message and choice.message.content:
            return choice.message.content.strip()
        return ""
    except Exception as e:
        logger.exception("Erro ao chamar OpenAI para análise por IA: %s", e)
        raise
