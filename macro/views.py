from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from accounts.mixins import PlanRequiredMixin, plan_required_api
from accounts.models import Plan
from macro.models import MacroScore, MacroVariation


def _parse_limit(request, default=50, max_limit=500):
    try:
        val = int(request.GET.get("limit", default))
    except (TypeError, ValueError):
        return default
    return max(1, min(val, max_limit))


class SinceInvalido(Exception):
    """`?since` que o cliente mandou não é uma data utilizável."""


def _parse_since(request):
    """
    Converte `?since` para datetime.

    `parse_datetime("2025-02-30T10:00:00")` levanta ValueError (dia 30 de
    fevereiro não existe) e a API respondia 500 para um erro do cliente.
    Datetime sem fuso também gerava RuntimeWarning e era interpretado no fuso
    local, silenciosamente.
    """
    raw = request.GET.get("since")
    if not raw:
        return None
    try:
        dt = parse_datetime(raw)
    except ValueError as exc:
        raise SinceInvalido(str(exc)) from exc
    if dt is None:
        raise SinceInvalido("formato de data não reconhecido")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _idade_do_dado(variacao) -> int:
    """
    Há quantos minutos é o número exibido.

    Quando a coleta falha, o painel repete o último valor conhecido. Sem esta
    informação, dado de horas atrás aparecia com a mesma cara de dado do
    minuto — o assinante não tinha como saber.
    """
    if variacao.status != "fallback":
        return 0
    marcador = variacao.block_reason or ""
    if marcador.startswith("last_known:") and marcador.endswith("min"):
        try:
            return int(marcador[len("last_known:") : -len("min")])
        except ValueError:
            return 0
    return 0


@require_GET
@plan_required_api(Plan.BASIC)
def latest_scores(request):
    limit = _parse_limit(request, default=100)
    qs = MacroScore.objects.order_by("-measurement_time")[:limit]
    data = [
        {
            "measurement_time": s.measurement_time,
            "total_score": s.total_score,
            "variation_sum": s.variation_sum,
        }
        for s in qs
    ]
    return JsonResponse({"results": data})


@require_GET
@plan_required_api(Plan.BASIC)
def latest_variations(request):
    limit = _parse_limit(request, default=200)
    try:
        since = _parse_since(request)
    except SinceInvalido as exc:
        return JsonResponse({"detail": f"Parâmetro 'since' inválido: {exc}"}, status=400)
    qs = MacroVariation.objects.select_related("asset").order_by("-measurement_time")
    if since:
        qs = qs.filter(measurement_time__gte=since)
    qs = qs[:limit]
    data = [
        {
            "asset": v.asset.name,
            "category": v.asset.category,
            "source_key": v.asset.source_key,
            "measurement_time": v.measurement_time,
            "variation_text": v.variation_text,
            "variation_decimal": v.variation_decimal,
            "status": v.status,
            "block_reason": v.block_reason,
            "market_phase": v.market_phase,
            # Minutos entre a coleta e a origem real do numero. Zero quando o
            # dado e do proprio ciclo; maior quando veio de fallback.
            "idade_minutos": _idade_do_dado(v),
        }
        for v in qs
    ]
    return JsonResponse({"results": data})


class SMCDashboardView(PlanRequiredMixin, TemplateView):
    """Página dedicada do Painel SMC (restrita a Basic/Premium)."""

    template_name = "macro/painel_smc.html"
    required_plan = Plan.BASIC


class SMCDashboardDemoView(PlanRequiredMixin, TemplateView):
    """Página demo do Painel SMC (restrita a Basic/Premium)."""

    template_name = "macro/painel_smc_demo.html"
    required_plan = Plan.BASIC


class SMCCleanView(PlanRequiredMixin, TemplateView):
    """Versão limpa do Painel SMC sem topo/menu (restrita a Basic/Premium)."""

    template_name = "macro/painel_smc_clean.html"
    required_plan = Plan.BASIC
