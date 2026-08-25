"""
Análise por IA em background.

Antes, a chamada à OpenAI acontecia dentro do request: até 90 segundos de
timeout, com 3 tentativas, ocupando um dos dois workers do gunicorn. Uma única
análise consumia metade da capacidade do site — e, com o timeout do gunicorn em
30s (corrigido depois), o worker era morto no meio e o usuário recebia 502 com
a OpenAI já cobrada.

Agora o request só cria a execução e enfileira. A página acompanha o andamento
e mostra o resultado quando fica pronto.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from trades.models import AIAnalyticsRun, AIRunStatus

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_ai_analysis(self, run_id: int) -> str:
    """
    Gera o relatório de uma execução já criada.

    Sem `autoretry_for`: o `run_analytics_llm` já trata as tentativas dos erros
    que valem retentar. Repetir aqui multiplicaria chamadas pagas por um erro
    que não vai passar (chave inválida, cota estourada).
    """
    from trades.ai_prompts import get_analytics_rules_text
    from trades.book_recommendations import get_book_recommendations_text
    from trades.llm_service import AnalyticsLLMError, run_analytics_llm
    from trades.services.analytics_ia import montar_contexto

    try:
        run = AIAnalyticsRun.objects.select_related("user").get(pk=run_id)
    except AIAnalyticsRun.DoesNotExist:
        logger.error("[trades] Execução de análise %s não existe.", run_id)
        return "run_inexistente"

    if run.status != AIRunStatus.PENDING:
        # Reentrega da mesma task: não refaz uma chamada paga.
        logger.info("[trades] Execução %s já está em %s; nada a fazer.", run_id, run.status)
        return "ja_processada"

    try:
        contexto = montar_contexto(run.user)
        texto = run_analytics_llm(contexto)
        if not (texto or "").strip():
            # Sem chave configurada ou resposta vazia: é falha, não análise.
            raise AnalyticsLLMError("A IA não retornou texto.")

        regras = get_analytics_rules_text(
            contexto.get("result_vs_technical_pct"),
            (contexto.get("advanced") or {}).get("win_rate"),
        )
        if regras:
            texto = texto + "\n\n" + regras

        livros = get_book_recommendations_text(
            contexto.get("top3_worst_combos") or [],
            url_smart_money_concept=getattr(settings, "BOOK_SMART_MONEY_CONCEPT_URL", "") or "",
            url_black_book=getattr(settings, "BOOK_BLACK_BOOK_URL", "") or "",
        )
        if livros:
            texto = texto + "\n\n" + livros

        run.result = texto
        run.status = AIRunStatus.SUCCESS
        run.save(update_fields=["result", "status"])
        logger.info("[trades] Análise %s concluída para user_id=%s", run_id, run.user_id)
        return AIRunStatus.SUCCESS

    except AnalyticsLLMError as exc:
        # O texto de erro não vai para `result`: apareceria na tela como se
        # fosse o resumo da IA e contaria como a análise da semana.
        run.status = AIRunStatus.FAILED
        run.error_detail = str(exc)[:2000] or "AnalyticsLLMError"
        run.save(update_fields=["status", "error_detail"])
        logger.warning("[trades] Análise %s falhou: %s", run_id, exc)
        return AIRunStatus.FAILED

    except Exception as exc:
        # Qualquer outra falha (banco, montagem do contexto) também precisa
        # deixar a execução num estado final: `pending` para sempre travaria o
        # usuário atrás do cooldown sem nunca mostrar resultado.
        run.status = AIRunStatus.FAILED
        run.error_detail = f"{type(exc).__name__}: {exc}"[:2000]
        run.save(update_fields=["status", "error_detail"])
        logger.exception("[trades] Erro inesperado na análise %s: %s", run_id, exc)
        return AIRunStatus.FAILED
