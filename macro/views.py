from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from accounts.mixins import PlanRequiredMixin
from accounts.models import Plan
from macro.models import MacroScore, MacroVariation


def _parse_limit(request, default=50, max_limit=500):
    try:
        val = int(request.GET.get("limit", default))
    except (TypeError, ValueError):
        return default
    return max(1, min(val, max_limit))


def _parse_since(request):
    raw = request.GET.get("since")
    if not raw:
        return None
    dt = parse_datetime(raw)
    return dt


@require_GET
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
def latest_variations(request):
    limit = _parse_limit(request, default=200)
    since = _parse_since(request)
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
        }
        for v in qs
    ]
    return JsonResponse({"results": data})


class SMCDashboardView(PlanRequiredMixin, TemplateView):
    """Página dedicada do Painel SMC (restrita a Basic/Premium)."""

    template_name = "macro/painel_smc.html"
    required_plan = Plan.BASIC


class SMCCleanView(PlanRequiredMixin, TemplateView):
    """Versão limpa do Painel SMC sem topo/menu (restrita a Basic/Premium)."""

    template_name = "macro/painel_smc_clean.html"
    required_plan = Plan.BASIC
