from django.contrib import admin
from django.db.models import Count
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from .models import GlobalAIAnalyticsRun, Trade


def operations_rank_view(request):
    """Ranking de usuários por total de operações registradas."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    ranking = (
        User.objects.filter(trades__isnull=False)
        .annotate(total_operacoes=Count("trades"))
        .order_by("-total_operacoes")
    )
    return render(
        request,
        "admin/trades/operations_rank.html",
        {"ranking": ranking, "title": "Rank de operações por usuário"},
    )


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_select_related = ("user",)
    list_display = (
        "executed_at",
        "user",
        "symbol",
        "market",
        "direction",
        "result_type",
        "profit_amount",
        "is_public",
        "display_as_anonymous",
        "screenshot_link",
    )
    list_filter = (
        "market",
        "direction",
        "trend",
        "result_type",
        "setup",
        "partial_trade",
        "is_public",
        "display_as_anonymous",
    )
    search_fields = (
        "symbol",
        "user__username",
        "user__email",
        "notes",
    )
    date_hierarchy = "executed_at"
    ordering = ("-executed_at",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "operations-rank/",
                self.admin_site.admin_view(operations_rank_view),
                name="trades_operations_rank",
            ),
        ]
        return custom + urls

    def screenshot_link(self, obj: Trade):
        if obj.screenshot:
            return format_html('<a href="{}" target="_blank">Abrir</a>', obj.screenshot.url)
        return "-"

    screenshot_link.short_description = "Captura"
    screenshot_link.admin_order_field = "screenshot"


@admin.register(GlobalAIAnalyticsRun)
class GlobalAIAnalyticsRunAdmin(admin.ModelAdmin):
    list_display = ("requested_at", "requested_by", "result_preview")
    list_filter = ("requested_at",)
    search_fields = ("result",)
    readonly_fields = ("requested_at", "requested_by", "result")
    date_hierarchy = "requested_at"
    ordering = ("-requested_at",)

    def result_preview(self, obj):
        if obj.result:
            return (obj.result[:80] + "...") if len(obj.result) > 80 else obj.result
        return "-"

    result_preview.short_description = "Resultado (preview)"
