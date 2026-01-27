from django.urls import path

from .views import AdvancedDashboardView, DashboardView, TradeCreateView, TradeDeleteView, TradeUpdateView

app_name = "trades"

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/avancado/", AdvancedDashboardView.as_view(), name="dashboard_advanced"),
    path("nova/", TradeCreateView.as_view(), name="trade_add"),
    path("editar/<int:pk>/", TradeUpdateView.as_view(), name="trade_edit"),
    path("deletar/<int:pk>/", TradeDeleteView.as_view(), name="trade_delete"),
]

