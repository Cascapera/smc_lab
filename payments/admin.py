from django.contrib import admin

from trader_portal.admin_site import admin_site

from .models import Payment, Subscription


@admin.register(Payment, site=admin_site)
class PaymentAdmin(admin.ModelAdmin):
    list_select_related = ("user",)
    list_display = (
        "created_at",
        "user",
        "plan",
        "amount",
        "currency",
        "status",
        "mp_payment_id",
    )
    list_filter = ("status", "plan", "currency")
    search_fields = (
        "user__username",
        "user__email",
        "mp_payment_id",
        "external_reference",
    )
    readonly_fields = ("raw_payload", "created_at", "updated_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(Subscription, site=admin_site)
class SubscriptionAdmin(admin.ModelAdmin):
    list_select_related = ("user",)
    list_display = (
        "created_at",
        "user",
        "plan",
        "plan_key",
        "amount",
        "status",
        "mp_preapproval_id",
    )
    list_filter = ("status", "plan")
    search_fields = (
        "user__username",
        "user__email",
        "mp_preapproval_id",
        "external_reference",
    )
    readonly_fields = ("raw_payload", "created_at", "updated_at")
    ordering = ("-created_at",)
