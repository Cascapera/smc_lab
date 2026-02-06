from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("planos/", views.PlanListView.as_view(), name="plans"),
    path("checkout/<str:plan>/", views.CreateCheckoutView.as_view(), name="checkout"),
    path("retorno/", views.PaymentReturnView.as_view(), name="return"),
    path("webhook/", views.MercadoPagoWebhookView.as_view(), name="webhook"),
    path("pagarme/webhook/", views.PagarmeWebhookView.as_view(), name="pagarme-webhook"),
]
