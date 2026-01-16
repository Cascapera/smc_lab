from django.contrib import admin
from django.utils.html import format_html

from .models import Trade


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
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

    def screenshot_link(self, obj: Trade):
        if obj.screenshot:
            return format_html('<a href="{}" target="_blank">Abrir</a>', obj.screenshot.url)
        return "-"

    screenshot_link.short_description = "Captura"
    screenshot_link.admin_order_field = "screenshot"
