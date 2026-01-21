from django.urls import path

from . import views

app_name = "macro"

urlpatterns = [
    path("painel/", views.SMCDashboardView.as_view(), name="painel"),
    path("painel/clean/", views.SMCCleanView.as_view(), name="painel_clean"),
    path("scores/", views.latest_scores, name="latest_scores"),
    path("variations/", views.latest_variations, name="latest_variations"),
]
