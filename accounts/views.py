from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .forms import ProfileForm, UserRegistrationForm


class RegisterView(View):
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "user_form": UserRegistrationForm(),
                "profile_form": ProfileForm(),
            },
        )

    def post(self, request):
        user_form = UserRegistrationForm(request.POST)
        profile_form = ProfileForm(request.POST)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile = user.profile
            cleaned_data = profile_form.cleaned_data
            for field, value in cleaned_data.items():
                setattr(profile, field, value)

            now = timezone.now()
            if profile.terms_accepted:
                profile.terms_accepted_at = now
            if profile.privacy_accepted:
                profile.privacy_accepted_at = now
            profile.save()

            messages.success(
                request,
                "Conta criada com sucesso! Faça login para continuar.",
            )
            return redirect(self.success_url)

        messages.error(request, "Por favor, corrija os erros abaixo.")
        return render(
            request,
            self.template_name,
            {
                "user_form": user_form,
                "profile_form": profile_form,
            },
        )
class LogoutView(View):
    """
    Faz logout imediatamente (GET ou POST) e redireciona para a landing.
    Evita a página padrão de confirmação do Django.
    """

    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect("landing")

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("landing")


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_obj"] = self.request.user
        context["profile"] = getattr(self.request.user, "profile", None)
        return context


class SessionStatusView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "unauthorized"}, status=401)
        last_login = request.user.last_login
        return JsonResponse(
            {
                "last_login": last_login.isoformat() if last_login else None,
                "last_login_ts": int(last_login.timestamp()) if last_login else None,
            }
        )
