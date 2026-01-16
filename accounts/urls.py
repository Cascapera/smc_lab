from django.contrib.auth import views as auth_views
from django.urls import path

from .views import LogoutView, RegisterView, ProfileView

app_name = "accounts"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("perfil/", ProfileView.as_view(), name="profile"),
]

