from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import Plan


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restringe acesso apenas a membros da equipe (is_staff ou is_superuser)."""

    def test_func(self):
        return getattr(self.request.user, "is_staff", False) or getattr(
            self.request.user, "is_superuser", False
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.warning(self.request, "Acesso restrito à equipe.")
        return redirect(reverse("trades:dashboard"))


def _get_insufficient_plan_message():
    """Mensagem lazy para evitar reverse() no carregamento do módulo (import circular)."""
    return mark_safe(
        "Recurso disponível apenas para os planos Basic, Premium e Premium+. "
        f'Assine um plano em <a href="{reverse("payments:plans")}">Planos</a> '
        'ou fale pelo <a href="https://wa.me/5511975743767" target="_blank" rel="noopener">'
        "WhatsApp</a>."
    )


class PlanRequiredMixin(LoginRequiredMixin):
    """Protege views por plano (free/basic/premium/premium_plus)."""

    required_plan: str = Plan.BASIC

    def get_required_plan(self) -> str:
        return self.required_plan

    def get_insufficient_message(self):
        """Subclasses podem sobrescrever para mensagem customizada (evitar reverse no load)."""
        return _get_insufficient_plan_message()

    def handle_no_permission(self):
        # Delega para LoginRequiredMixin quando não autenticado
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        messages.warning(self.request, self.get_insufficient_message())
        return redirect(reverse("trades:dashboard"))

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            profile = getattr(request.user, "profile", None)
            if profile is None or not profile.has_plan_at_least(self.get_required_plan()):
                return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def plan_required(required_plan: str = Plan.BASIC):
    """Decorator para views baseadas em função."""

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Respeita login_required padrão
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())

            profile = getattr(request.user, "profile", None)
            if profile and profile.has_plan_at_least(required_plan):
                return view_func(request, *args, **kwargs)

            messages.warning(
                request,
                _get_insufficient_plan_message(),
            )
            return redirect(reverse("trades:dashboard"))

        return _wrapped_view

    return decorator
