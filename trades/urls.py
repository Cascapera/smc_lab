from django.urls import path

from .views import AdvancedDashboardView, DashboardView, TradeCreateView

app_name = "trades"

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/avancado/", AdvancedDashboardView.as_view(), name="dashboard_advanced"),
    path("nova/", TradeCreateView.as_view(), name="trade_add"),
]

