"""
Métricas que alimentam a análise por IA.

Extraído de `AnalyticsIAView.get_context_data` porque a análise deixou de rodar
dentro do request: a task do Celery precisa montar exatamente o mesmo contexto,
e duas cópias da mesma conta divergiriam na primeira alteração.

Só entra aqui o que o prompt usa. A parte de apresentação (paginação da tabela,
gráfico por horário, listas de choices) continua na view.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from trades.analytics import compute_advanced_metrics, compute_user_dashboard
from trades.models import (
    EntryType,
    HighTimeFrame,
    PartialTrade,
    RegionHTF,
    Setup,
    SMCPanel,
    Trade,
    Trend,
    Trigger,
)

CAMPOS_DA_COMBINACAO = [
    "setup",
    "entry_type",
    "high_time_frame",
    "region_htf",
    "trend",
    "smc_panel",
    "trigger",
    "partial_trade",
]


def _rotulos() -> dict[str, dict]:
    return {
        "setup": dict(Setup.choices),
        "entry_type": dict(EntryType.choices),
        "high_time_frame": dict(HighTimeFrame.choices),
        "region_htf": dict(RegionHTF.choices),
        "trend": dict(Trend.choices),
        "smc_panel": dict(SMCPanel.choices),
        "trigger": dict(Trigger.choices),
        "partial_trade": dict(PartialTrade.choices),
    }


def trades_do_usuario(user):
    """Trades que entram na análise, respeitando o último zeramento de conta."""
    trades_qs = Trade.objects.filter(user=user).order_by("executed_at")
    profile = getattr(user, "profile", None)
    if profile and profile.last_reset_at:
        trades_qs = trades_qs.filter(executed_at__gte=profile.last_reset_at)
    return trades_qs


def _linhas_de_combinacao(brutas: list[dict]) -> list[dict]:
    rotulos = _rotulos()
    return [
        {
            **{campo: linha[campo] for campo in CAMPOS_DA_COMBINACAO},
            "total": linha["total"],
            "labels": {
                campo: rotulos[campo].get(linha[campo], linha[campo] or "N/D")
                for campo in CAMPOS_DA_COMBINACAO
            },
        }
        for linha in brutas
    ]


def combinacoes(trades_qs) -> tuple[list[dict], list[dict], list[dict]]:
    """
    As 3 melhores e as 3 piores combinações de características.

    As piores são filtradas por `total < 0`. Sem esse filtro, um usuário sem
    nenhuma combinação negativa recebia as três MENOS lucrativas como se fossem
    prejuízo — e o texto dizia para parar de operá-las.
    """
    agregado = trades_qs.values(*CAMPOS_DA_COMBINACAO).annotate(
        total=Coalesce(Sum("profit_amount"), Decimal("0"))
    )
    melhores_brutas = list(agregado.order_by("-total")[:3])
    piores_brutas = list(
        trades_qs.values(*CAMPOS_DA_COMBINACAO)
        .annotate(total=Coalesce(Sum("profit_amount"), Decimal("0")))
        .filter(total__lt=0)
        .order_by("total")[:3]
    )
    return (
        _linhas_de_combinacao(melhores_brutas),
        _linhas_de_combinacao(piores_brutas),
        piores_brutas,
    )


def melhora_possivel(total_profit, piores_brutas: list[dict]) -> dict:
    """
    Quanto o resultado melhoraria sem as combinações negativas.

    `improvement_pct` fica None quando o resultado acumulado é zero: dividir por
    1 (o que o código fazia) transformava R$ 300 em "melhora de 30000%".
    """
    soma_das_piores = sum(float(linha["total"]) for linha in piores_brutas)
    ganho = abs(min(0.0, soma_das_piores))
    novo_total = float(total_profit) + ganho

    if total_profit and float(total_profit) != 0:
        percentual = round(ganho / abs(float(total_profit)) * 100, 2)
    else:
        percentual = None

    return {
        "improvement_reais": round(ganho, 2),
        "improvement_new_total": round(novo_total, 2),
        "improvement_pct": percentual,
    }


def resultado_sobre_ganho_tecnico(trades_qs, total_profit) -> float | None:
    agregado = trades_qs.aggregate(
        total_technical=Coalesce(Sum("technical_gain"), Decimal("0")),
    )
    total_tecnico = agregado["total_technical"]
    if total_tecnico and float(total_tecnico) != 0:
        return round(float(total_profit) / float(total_tecnico) * 100, 2)
    return None


def montar_contexto(user) -> dict:
    """
    Contexto completo da análise. Usado pela view (para renderizar) e pela task
    do Celery (para montar o prompt), garantindo que os dois vejam o mesmo.
    """
    base = compute_user_dashboard(user)
    trades_qs = trades_do_usuario(user)

    avancado = compute_advanced_metrics(
        trades_qs,
        base.get("balance_series", []),
        base["summary"]["initial_balance"],
        base["summary"],
    )

    melhores, piores, piores_brutas = combinacoes(trades_qs)
    total_profit = base["summary"]["total_profit"]

    contexto = {
        "dashboard": base,
        "advanced": avancado,
        "trades_qs": trades_qs,
        "top3_best_combos": melhores,
        "top3_worst_combos": piores,
        "result_vs_technical_pct": resultado_sobre_ganho_tecnico(trades_qs, total_profit),
    }
    contexto.update(melhora_possivel(total_profit, piores_brutas))
    return contexto
