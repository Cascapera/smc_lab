from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .views import (
    LogoutView,
    ProfileEditView,
    ProfileView,
    RegisterView,
    SessionStatusView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("perfil/", ProfileView.as_view(), name="profile"),
    path("perfil/editar/", ProfileEditView.as_view(), name="profile_edit"),
    path("session-status/", SessionStatusView.as_view(), name="session_status"),
    # Recuperação de senha por e-mail (GoDaddy SMTP)
    path(
        "recuperar-senha/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "recuperar-senha/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "recuperar-senha/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "recuperar-senha/concluido/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
