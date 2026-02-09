"""
Comando de teste: monta dados de exemplo, chama a LLM e monta o texto completo
(resposta LLM + regras Result/Técnico e Win rate + bloco de livros).
Uso: python manage.py test_analytics_llm
"""
from __future__ import annotations

import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from trades.ai_prompts import build_analytics_user_prompt, get_analytics_rules_text
from trades.book_recommendations import get_book_recommendations_text
from trades.llm_service import run_analytics_llm


def get_mock_context():
    """Dados de exemplo no mesmo formato enviado pela view para a LLM."""
    return {
        "top3_best_combos": [
            {
                "total": 1250.50,
                "labels": {
                    "setup": "CHOCH",
                    "entry_type": "Confirmado",
                    "high_time_frame": "15 min",
                    "region_htf": "Primária",
                    "trend": "A favor",
                    "smc_panel": "A favor",
                    "trigger": "Passagem",
                    "partial_trade": "Não fiz",
                },
            },
            {
                "total": 890.00,
                "labels": {
                    "setup": "FVG",
                    "entry_type": "Confirmado",
                    "high_time_frame": "60 min",
                    "region_htf": "Primária",
                    "trend": "A favor",
                    "smc_panel": "A favor",
                    "trigger": "Região",
                    "partial_trade": "Sim +5x1",
                },
            },
            {
                "total": 620.30,
                "labels": {
                    "setup": "Continuação",
                    "entry_type": "Confirmado",
                    "high_time_frame": "15 min",
                    "region_htf": "Secundária",
                    "trend": "A favor",
                    "smc_panel": "Neutro",
                    "trigger": "Passagem",
                    "partial_trade": "Não fiz",
                },
            },
        ],
        "top3_worst_combos": [
            {
                "total": -450.00,
                "setup": "flip",
                "entry_type": "anticipated",
                "high_time_frame": "5",
                "region_htf": "none",
                "trend": "bearish",
                "smc_panel": "pessimistic",
                "trigger": "none",
                "partial_trade": "not_available",
                "labels": {
                    "setup": "Flip",
                    "entry_type": "Antecipado",
                    "high_time_frame": "5 min",
                    "region_htf": "N/D",
                    "trend": "Contra",
                    "smc_panel": "Contra",
                    "trigger": "N/A",
                    "partial_trade": "Sem parcial",
                },
            },
            {
                "total": -320.50,
                "setup": "fvg",
                "entry_type": "anticipated",
                "high_time_frame": "5",
                "region_htf": "secondary",
                "trend": "range",
                "smc_panel": "neutral",
                "trigger": "rocadinha",
                "partial_trade": "yes_neg",
                "labels": {
                    "setup": "FVG",
                    "entry_type": "Antecipado",
                    "high_time_frame": "5 min",
                    "region_htf": "Secundária",
                    "trend": "Lateral",
                    "smc_panel": "Neutro",
                    "trigger": "Roçadinha",
                    "partial_trade": "Sim -5x1",
                },
            },
            {
                "total": -180.00,
                "setup": "choch",
                "entry_type": "anticipated",
                "high_time_frame": "5",
                "region_htf": "none",
                "trend": "bearish",
                "smc_panel": "pessimistic",
                "trigger": "none",
                "partial_trade": "not_available",
                "labels": {
                    "setup": "CHOCH",
                    "entry_type": "Antecipado",
                    "high_time_frame": "5 min",
                    "region_htf": "N/D",
                    "trend": "Contra",
                    "smc_panel": "Contra",
                    "trigger": "N/A",
                    "partial_trade": "Sem parcial",
                },
            },
        ],
        "advanced": {
            "win_rate": 58.5,
            "profit_factor": 1.42,
            "total_profit": 840.30,
        },
        "improvement_reais": 950.50,
        "improvement_new_total": 1790.80,
        "improvement_pct": 113.18,
        # Para as regras fixas: % resultado/ganho técnico (55 = abaixo de 60%, aciona a regra "parciais mais longas")
        "result_vs_technical_pct": 55,
    }


class Command(BaseCommand):
    help = (
        "Testa a análise completa: LLM + regras (Result/Técnico e Win rate) + livros. "
        "Exibe o texto como o usuário verá na tela."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Não chama a LLM; monta só regras + livros com texto fake da LLM.",
        )

    def handle(self, *args, **options):
        # UTF-8 no terminal (evita UnicodeEncodeError no Windows com caracteres como →)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")

        context = get_mock_context()
        no_llm = options.get("no_llm", False)

        if not no_llm and not (getattr(settings, "OPENAI_API_KEY", "") or "").strip():
            self.stderr.write(
                self.style.ERROR("OPENAI_API_KEY não está definida no .env. Use --no-llm para ver só regras + livros.")
            )
            return

        result_text = ""
        if no_llm:
            result_text = (
                "Regra: Priorize entradas confirmadas em HTF maior e evite antecipado em 5 min.\n"
                "Ponto forte: Sua consistência em CHOCH e FVG em tendência a favor.\n"
                "Ponto fraco: Operações antecipadas em 5 min e tendência contra.\n"
                "Próximo passo: Limite a 2 operações por dia na próxima semana e só entre confirmado."
            )
            self.stdout.write(self.style.WARNING("--- Modo --no-llm: usando texto fake da LLM ---"))
        else:
            user_prompt = build_analytics_user_prompt(context)
            self.stdout.write(self.style.MIGRATE_HEADING("--- Prompt enviado à LLM ---"))
            self.stdout.write(user_prompt)
            self.stdout.write("")
            try:
                result_text = run_analytics_llm(context) or ""
                self.stdout.write(self.style.SUCCESS("--- Resposta da LLM ---"))
                self.stdout.write(result_text)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Erro na chamada à LLM: {e}"))
                return

        rules_text = get_analytics_rules_text(
            context.get("result_vs_technical_pct"),
            (context.get("advanced") or {}).get("win_rate"),
        )
        if rules_text:
            result_text = (result_text or "") + "\n\n" + rules_text

        url_smc = getattr(settings, "BOOK_SMART_MONEY_CONCEPT_URL", "") or ""
        url_black = getattr(settings, "BOOK_BLACK_BOOK_URL", "") or ""
        book_text = get_book_recommendations_text(
            context.get("top3_worst_combos") or [],
            url_smart_money_concept=url_smc,
            url_black_book=url_black,
        )
        if book_text:
            result_text = (result_text or "") + "\n\n" + book_text

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("========== TEXTO COMPLETO (como na tela) =========="))
        self.stdout.write(result_text)
