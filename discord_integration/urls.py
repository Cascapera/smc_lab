from django.urls import path

from . import views

app_name = "discord"

urlpatterns = [
    path("login/", views.DiscordLoginView.as_view(), name="login"),
    path("callback/", views.DiscordCallbackView.as_view(), name="callback"),
    path("unlink/", views.DiscordUnlinkView.as_view(), name="unlink"),
]
