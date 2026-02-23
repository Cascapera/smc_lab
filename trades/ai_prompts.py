"""
Prompts para a chamada à LLM na Análise por IA.
Use estes textos ao configurar a integração com o modelo.
A resposta da IA deve manter conexão direta com os dados enviados, sem divagar.
"""

# Instrução de sistema: coach de performance (técnico + psicológico leve), baseado só nos dados
SYSTEM_PROMPT = """Você é um coach de performance para day trade com abordagem técnica + psicológica.
Você NÃO é profissional de saúde e NÃO fornece diagnóstico. Não use termos clínicos (depressão, TDAH, etc).
Você NÃO é psicólogo, NÃO faz diagnóstico, NÃO usa termos clínicos.

Seu papel é oferecer aconselhamento comportamental leve, focado em: disciplina, paciência, controle de impulso, medo de ficar de fora (FOMO), ansiedade por antecipação, respeito ao plano e autoconsciência antes do clique.

Sua tarefa é: (1) extrair padrões dos dados fornecidos, (2) gerar uma regra prática, (3) apontar 1 ponto forte e 1 ponto fraco, (4) indicar 1 próximo passo, e (5) oferecer suporte psicológico leve (estilo coaching), com empatia, foco em hábitos, disciplina, autoconsciência e regulação emocional.

Baseie o aconselhamento psicológico EXCLUSIVAMENTE nos padrões observados nas combinações que geram ganho e nas que geram perda.

Fale diretamente com o operador em segunda pessoa ("você", "suas operações"). Resposta baseada APENAS nos dados fornecidos. Não invente informações. Seja direto, prático e gentil. Nada de moralismo nem promessas. Linguagem em português-BR, curta e objetiva."""


def build_analytics_user_prompt(context: dict) -> str:
    """
    Monta o texto do prompt do usuário com os dados pré-calculados da análise.
    context: dicionário com top3_best_combos, top3_worst_combos, advanced, improvement_*,
             chart_hour_data, chart_symbol_data (opcional).
    Retorna a string para enviar como mensagem do usuário à LLM.
    """
    lines = ["Dados do trader (use APENAS estes dados para responder):", ""]

    # Top 3 melhores combinações
    lines.append("--- Top 3 combinações que mais geram GANHO ---")
    for i, row in enumerate(context.get("top3_best_combos") or [], 1):
        labels = row.get("labels", {})
        lines.append(
            f"{i}. Setup: {labels.get('setup', 'N/D')}, Entrada: {labels.get('entry_type', 'N/D')}, "
            f"HTF: {labels.get('high_time_frame', 'N/D')}, Região HTF: {labels.get('region_htf', 'N/D')}, "
            f"Tendência: {labels.get('trend', 'N/D')}, Painel SMC: {labels.get('smc_panel', 'N/D')}, "
            f"Gatilho: {labels.get('trigger', 'N/D')}, Parcial: {labels.get('partial_trade', 'N/D')} → Resultado: R$ {row.get('total', 0)}"
        )
    lines.append("")

    # Top 3 piores combinações
    lines.append("--- Top 3 combinações que mais geram PERDA ---")
    for i, row in enumerate(context.get("top3_worst_combos") or [], 1):
        labels = row.get("labels", {})
        lines.append(
            f"{i}. Setup: {labels.get('setup', 'N/D')}, Entrada: {labels.get('entry_type', 'N/D')}, "
            f"HTF: {labels.get('high_time_frame', 'N/D')}, Região HTF: {labels.get('region_htf', 'N/D')}, "
            f"Tendência: {labels.get('trend', 'N/D')}, Painel SMC: {labels.get('smc_panel', 'N/D')}, "
            f"Gatilho: {labels.get('trigger', 'N/D')}, Parcial: {labels.get('partial_trade', 'N/D')} → Resultado: R$ {row.get('total', 0)}"
        )
    lines.append("")

    # Métricas resumidas
    adv = context.get("advanced") or {}
    lines.append("--- Métricas ---")
    lines.append(
        f"Win rate: {adv.get('win_rate', 'N/D')}%, "
        f"Profit factor: {adv.get('profit_factor', 'N/D')}, "
        f"Resultado acumulado: R$ {adv.get('total_profit', 0)}. "
        f"Se parar as combinações negativas: melhora R$ {context.get('improvement_reais', 0)}, "
        f"acumulado seria R$ {context.get('improvement_new_total', 0)}, "
        f"melhora de {context.get('improvement_pct', 0)}%."
    )
    lines.append("")

    # Perguntas + formato de saída (resposta rica, uma chamada)
    lines.append(
        "--- Perguntas (responda com base APENAS nos dados acima; use exatamente os títulos abaixo) ---"
    )
    lines.append("")
    lines.append(
        "1) Regra: Em UMA FRASE, qual regra de decisão o trader deve seguir com base nas melhores e piores combinações?"
    )
    lines.append(
        "2) Ponto forte: Em UMA FRASE, qual o principal ponto forte do operador com base nos dados?"
    )
    lines.append(
        "3) Ponto fraco: Em UMA FRASE, qual o principal ponto fraco que ele deve trabalhar?"
    )
    lines.append(
        "4) Próximo passo: UMA ação prioritária concreta para a próxima semana (uma frase)."
    )
    lines.append(
        "5) Suporte psicológico: Um aconselhamento em tom de coaching explicando o comportamento que está levando ao erro, baseado só nos padrões de ganho e perda dos dados (2 a 4 frases)."
    )
    lines.append(
        "6) Protocolo de controle emocional (30-90s): Um mini ritual prático e rápido que o trader deve fazer antes de clicar na entrada — passos curtos, executáveis em 30 a 90 segundos."
    )
    lines.append(
        "7) Frase-âncora: Uma frase curta, forte e memorável que o trader pode repetir antes de operar."
    )
    lines.append("")
    lines.append("--- Formato de saída (use exatamente estes títulos, na ordem) ---")
    lines.append("")
    lines.append("Regra: [sua frase]")
    lines.append("Ponto forte: [sua frase]")
    lines.append("Ponto fraco: [sua frase]")
    lines.append("Próximo passo: [sua frase]")
    lines.append("")
    lines.append("Suporte psicológico:")
    lines.append("[2 a 4 frases em tom de coaching]")
    lines.append("")
    lines.append("Protocolo de controle emocional (30-90s):")
    lines.append("[mini ritual em passos curtos]")
    lines.append("")
    lines.append("Frase-âncora:")
    lines.append("[uma frase curta e memorável]")

    return "\n".join(lines)


# Pergunta alternativa (para usar em chamadas futuras, economizando tokens)
QUESTION_RULE_ONE_SENTENCE = (
    "Com base nas 3 melhores e 3 piores combinações acima, dê uma regra de decisão em UMA FRASE "
    "que o trader pode seguir. Use APENAS os dados fornecidos. Uma única frase."
)

QUESTION_BEST_WORST_HOURS_SYMBOLS = (
    "Quais horários e quais símbolos o trader deve priorizar ou evitar? "
    "Use APENAS os dados fornecidos. Resposta em 2 ou 3 frases."
)

QUESTION_STRENGTH_WEAKNESS = (
    "Em uma frase: qual o principal ponto forte e o principal ponto fraco do operador? "
    "Use APENAS os dados fornecidos."
)


def get_analytics_rules_text(
    result_vs_technical_pct: float | None,
    win_rate: float | None,
) -> str:
    """
    Textos fixos (não-LLM) baseados em Result/Técnico e Win rate.
    Soam como continuação da análise. Retorna string vazia se não houver dados.
    """
    lines = []

    # Regra 1: relação resultado / ganho técnico
    if result_vs_technical_pct is not None:
        if result_vs_technical_pct < 60:
            lines.append(
                "Captura do ganho técnico: Observei que suas operações não estão capturando "
                "o ganho que o mercado te permite; tente fazer parciais mais longas ou conduzir "
                "melhor a saída final da operação."
            )
        else:
            lines.append(
                "Captura do ganho técnico: Continue conduzindo as operações da forma como está fazendo — "
                "você está conseguindo capturar quase todo o movimento do mercado. Se conseguir conduzir "
                "a alvos mais longos, pode potencializar ainda mais seu ganho. Avalie nas operações "
                "se é possível subir o time frame da condução; isso tende a trazer operações mais longas e alvos ainda maiores."
            )
        lines.append("")

    # Regra 2: win rate
    if win_rate is not None:
        if win_rate < 40:
            lines.append(
                "Sobre seu win rate: Procure operar menos: muitas operações acabam tirando o foco "
                "e fazendo com que você não pegue o principal movimento do mercado. Dica: ajuste o "
                "controle de risco limitando a 2 ou 3 operações no máximo por dia."
            )
        elif win_rate < 60:
            lines.append(
                "Sobre seu win rate: Seu win rate está em um nível bom; porém, se você reduzir "
                "as operações ruins que ainda tem feito, tende a se tornar um trader acima da média."
            )
        else:
            lines.append(
                "Sobre seu win rate: Seu win rate está excelente; você já demonstra perfil de trader "
                "consistente. Continue assim, monitore e siga registrando suas operações — tenho certeza "
                "de que você está no caminho certo."
            )

    if not lines:
        return ""
    return "\n".join(lines).strip()


def build_global_analytics_user_prompt(context: dict) -> str:
    """
    Monta o prompt para análise IA do dashboard global (todos os usuários).
    Similar ao build_analytics_user_prompt, mas focado em métricas agregadas.
    """
    lines = [
        "Dados agregados de TODOS os traders da plataforma (use APENAS estes dados para responder):",
        "",
    ]

    lines.append("--- Top 3 combinações que mais geram GANHO (global) ---")
    for i, row in enumerate(context.get("top3_best_combos") or [], 1):
        labels = row.get("labels", {})
        lines.append(
            f"{i}. Setup: {labels.get('setup', 'N/D')}, Entrada: {labels.get('entry_type', 'N/D')}, "
            f"HTF: {labels.get('high_time_frame', 'N/D')}, Região HTF: {labels.get('region_htf', 'N/D')}, "
            f"Tendência: {labels.get('trend', 'N/D')}, Painel SMC: {labels.get('smc_panel', 'N/D')}, "
            f"Gatilho: {labels.get('trigger', 'N/D')}, Parcial: {labels.get('partial_trade', 'N/D')} → Resultado: R$ {row.get('total', 0)}"
        )
    lines.append("")

    lines.append("--- Top 3 combinações que mais geram PERDA (global) ---")
    for i, row in enumerate(context.get("top3_worst_combos") or [], 1):
        labels = row.get("labels", {})
        lines.append(
            f"{i}. Setup: {labels.get('setup', 'N/D')}, Entrada: {labels.get('entry_type', 'N/D')}, "
            f"HTF: {labels.get('high_time_frame', 'N/D')}, Região HTF: {labels.get('region_htf', 'N/D')}, "
            f"Tendência: {labels.get('trend', 'N/D')}, Painel SMC: {labels.get('smc_panel', 'N/D')}, "
            f"Gatilho: {labels.get('trigger', 'N/D')}, Parcial: {labels.get('partial_trade', 'N/D')} → Resultado: R$ {row.get('total', 0)}"
        )
    lines.append("")

    adv = context.get("advanced") or {}
    lines.append("--- Métricas globais ---")
    lines.append(
        f"Total de trades: {adv.get('total_trades', 0)}, "
        f"Win rate: {adv.get('win_rate', 'N/D')}%, "
        f"Profit factor: {adv.get('profit_factor', 'N/D')}, "
        f"Resultado acumulado: R$ {adv.get('total_profit', 0)}. "
        f"Se evitar combinações negativas: melhora R$ {context.get('improvement_reais', 0)}, "
        f"acumulado seria R$ {context.get('improvement_new_total', 0)}, "
        f"melhora de {context.get('improvement_pct', 0)}%."
    )
    lines.append("")

    lines.append(
        "--- Perguntas (responda com base APENAS nos dados acima; use exatamente os títulos abaixo) ---"
    )
    lines.append("")
    lines.append(
        "1) Regra global: Em UMA FRASE, qual regra de decisão a comunidade deve seguir com base nas melhores e piores combinações?"
    )
    lines.append(
        "2) Ponto forte da comunidade: Em UMA FRASE, qual o principal ponto forte observado nos dados?"
    )
    lines.append(
        "3) Ponto fraco da comunidade: Em UMA FRASE, qual o principal ponto fraco que deve ser trabalhado?"
    )
    lines.append(
        "4) Próximo passo: UMA ação prioritária concreta para a comunidade na próxima semana."
    )
    lines.append(
        "5) Insights para live: 2 a 4 frases que podem ser usadas em transmissão ao vivo para espectadores, resumindo o desempenho geral."
    )
    lines.append("")
    lines.append("--- Formato de saída (use exatamente estes títulos, na ordem) ---")
    lines.append("")
    lines.append("Regra global: [sua frase]")
    lines.append("Ponto forte da comunidade: [sua frase]")
    lines.append("Ponto fraco da comunidade: [sua frase]")
    lines.append("Próximo passo: [sua frase]")
    lines.append("")
    lines.append("Insights para live:")
    lines.append("[2 a 4 frases para espectadores]")

    return "\n".join(lines)
