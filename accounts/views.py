from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import PasswordResetView as DjangoPasswordResetView
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django_ratelimit.decorators import ratelimit

from .forms import (
    AsyncPasswordResetForm,
    EmailAuthenticationForm,
    ProfileEditForm,
    ProfileForm,
    UserRegistrationForm,
)
from .ratelimit import client_ip_key

logger = logging.getLogger(__name__)

User = get_user_model()


def _rate_limit_exceeded(request):
    """Redireciona com mensagem quando rate limit é excedido."""
    messages.warning(
        request,
        "Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.",
    )
    return redirect(reverse("accounts:login"))


@method_decorator(
    ratelimit(key=client_ip_key, rate="5/m", method="POST", block=False),
    name="post",
)
class LoginView(DjangoLoginView):
    """Login com rate limiting (5 tentativas/minuto por IP real do cliente).

    A chave vem de `client_ip_key`, e não do `key="ip"` do django-ratelimit:
    atrás do nginx o `REMOTE_ADDR` é sempre o do proxy, o que tornava o limite
    global — cinco tentativas bloqueavam o login de todos os usuários.
    """

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm

    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            return _rate_limit_exceeded(request)
        return super().post(request, *args, **kwargs)


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

    @method_decorator(
        ratelimit(key=client_ip_key, rate="3/m", method="POST", block=False),
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return _rate_limit_exceeded(request)
        user_form = UserRegistrationForm(request.POST)
        profile_form = ProfileForm(request.POST)

        if user_form.is_valid() and profile_form.is_valid():
            try:
                user = user_form.save()
            except IntegrityError:
                # `clean_email` já barra o duplicado, mas duas requisições
                # simultâneas com o mesmo e-mail passam as duas pela validação.
                # Sem isto, a perdedora vira 500 no cadastro.
                logger.warning("[accounts] Cadastro simultâneo com e-mail duplicado.")
                user_form.add_error("email", "Já existe uma conta cadastrada com este e-mail.")
                return render(
                    request,
                    self.template_name,
                    {"user_form": user_form, "profile_form": profile_form},
                )
            profile = user.profile
            cleaned_data = profile_form.cleaned_data
            for field, value in cleaned_data.items():
                setattr(profile, field, value)

            # `current_balance` saiu do formulário (é derivado). No cadastro
            # não há trades, então ele começa igual ao saldo inicial.
            profile.current_balance = profile.initial_balance

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


@method_decorator(
    ratelimit(key=client_ip_key, rate="5/h", method="POST", block=False),
    name="post",
)
@method_decorator(
    # Segundo balde, por destinatário: sem ele, uma botnet com IPs diferentes
    # ainda esgota a cota de envio da GoDaddy contra um único e-mail e enche a
    # caixa de quem nunca pediu recuperação nenhuma.
    ratelimit(key="post:email", rate="3/h", method="POST", block=False),
    name="post",
)
class PasswordResetView(DjangoPasswordResetView):
    """Recuperação de senha com rate limit e envio fora do request.

    Antes eram 500 POSTs = 500 e-mails via GoDaddy (cota baixa), cada um
    segurando um worker pelo tempo do SMTP.
    """

    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    form_class = AsyncPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")

    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            messages.warning(
                request,
                "Muitas solicitações de recuperação. Aguarde alguns minutos antes de "
                "tentar novamente.",
            )
            return redirect(reverse("accounts:password_reset"))
        return super().post(request, *args, **kwargs)


class LogoutView(View):
    """
    Logout só por POST, sem a página de confirmação do Django.

    Aceitar GET permitia deslogar o usuário de qualquer site: bastava um
    `<img src="https://.../accounts/logout/">` numa página que ele abrisse. Foi
    por isso que o Django 5 removeu o logout por GET.

    Um GET aqui não é erro do usuário — é link antigo ou favorito —, então
    redireciona para a landing em vez de responder 405.
    """

    def get(self, request, *args, **kwargs):
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


class ProfileEditView(LoginRequiredMixin, View):
    template_name = "accounts/profile_edit.html"

    def get(self, request):
        profile = getattr(request.user, "profile", None)
        form = ProfileEditForm(instance=profile)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        profile = getattr(request.user, "profile", None)
        form = ProfileEditForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado com sucesso!")
            return redirect("accounts:profile")
        messages.error(request, "Por favor, corrija os erros abaixo.")
        return render(request, self.template_name, {"form": form})


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
