from django.urls import path

from .views import (
    AdvancedDashboardView,
    AnalyticsIAView,
    DashboardView,
    GlobalAnalyticsIAView,
    GlobalDashboardView,
    TradeCreateView,
    TradeDeleteView,
    TradeScreenshotView,
    TradeUpdateView,
)

app_name = "trades"

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/avancado/", AdvancedDashboardView.as_view(), name="dashboard_advanced"),
    path("dashboard/avancado/analise-ia/", AnalyticsIAView.as_view(), name="analytics_ia"),
    path("dashboard/global/", GlobalDashboardView.as_view(), name="dashboard_global"),
    path(
        "dashboard/global/analise-ia/", GlobalAnalyticsIAView.as_view(), name="analytics_ia_global"
    ),
    path("nova/", TradeCreateView.as_view(), name="trade_add"),
    path("editar/<int:pk>/", TradeUpdateView.as_view(), name="trade_edit"),
    path("deletar/<int:pk>/", TradeDeleteView.as_view(), name="trade_delete"),
    path("captura/<int:pk>/", TradeScreenshotView.as_view(), name="trade_screenshot"),
]
