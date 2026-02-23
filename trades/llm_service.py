"""
Serviço de chamada à OpenAI para a Análise por IA.
Usa GPT-4o mini por padrão (custo baixo, boa qualidade).
"""

from __future__ import annotations

import logging
import time

from django.conf import settings

from .ai_prompts import (
    SYSTEM_PROMPT,
    build_analytics_user_prompt,
    build_global_analytics_user_prompt,
)

logger = logging.getLogger(__name__)

# Timeout em segundos para chamadas à API
OPENAI_TIMEOUT = 90

# Retry: máximo de tentativas e delay base (segundos)
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2


class AnalyticsLLMError(Exception):
    """Exceção levantada quando a geração do relatório por IA falha."""

    pass


def _call_openai(
    client,
    model: str,
    system_content: str,
    user_content: str,
) -> str:
    """Executa a chamada à API com timeout e retorna o conteúdo da resposta."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        max_tokens=1000,
        temperature=0.3,
    )
    choice = response.choices[0] if response.choices else None
    if choice and choice.message and choice.message.content:
        return choice.message.content.strip()
    return ""


def run_analytics_llm(context: dict) -> str:
    """
    Chama a OpenAI com o contexto da análise e retorna a resposta em texto.
    context: dicionário com top3_best_combos, top3_worst_combos, advanced,
             improvement_reais, improvement_new_total, improvement_pct.
    Levanta AnalyticsLLMError em caso de falha (erros são logados).
    Retorna string vazia se API key não configurada.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key.strip():
        logger.warning("OPENAI_API_KEY não configurada; análise por IA não executada.")
        return ""

    model = getattr(settings, "OPENAI_ANALYTICS_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    user_content = build_analytics_user_prompt(context)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT)
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                return _call_openai(client, model, SYSTEM_PROMPT, user_content)
            except Exception as e:
                last_error = e
                logger.exception(
                    "Erro ao chamar OpenAI para análise por IA (tentativa %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                )
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.info("Aguardando %ds antes de retentar...", delay)
                    time.sleep(delay)

        raise AnalyticsLLMError from last_error
    except AnalyticsLLMError:
        raise
    except Exception as e:
        logger.exception("Erro inesperado ao chamar OpenAI para análise por IA: %s", e)
        raise AnalyticsLLMError from e


def run_global_analytics_llm(context: dict) -> str:
    """
    Chama a OpenAI com o contexto da análise global e retorna a resposta em texto.
    Usa prompt específico para métricas agregadas de todos os usuários.
    Levanta AnalyticsLLMError em caso de falha (erros são logados).
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key.strip():
        logger.warning("OPENAI_API_KEY não configurada; análise por IA não executada.")
        return ""

    model = getattr(settings, "OPENAI_ANALYTICS_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    system_prompt = (
        "Você é um analista de performance para uma comunidade de day traders. "
        "Sua tarefa é analisar dados agregados (sem identificar indivíduos) e extrair "
        "padrões, regras e insights que possam ser úteis para a comunidade e para "
        "transmissões ao vivo. Seja direto, prático e objetivo. Use APENAS os dados fornecidos. "
        "Linguagem em português-BR."
    )
    user_content = build_global_analytics_user_prompt(context)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT)
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                return _call_openai(client, model, system_prompt, user_content)
            except Exception as e:
                last_error = e
                logger.exception(
                    "Erro ao chamar OpenAI para análise global por IA (tentativa %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                )
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.info("Aguardando %ds antes de retentar...", delay)
                    time.sleep(delay)

        raise AnalyticsLLMError from last_error
    except AnalyticsLLMError:
        raise
    except Exception as e:
        logger.exception("Erro inesperado ao chamar OpenAI para análise global por IA: %s", e)
        raise AnalyticsLLMError from e
