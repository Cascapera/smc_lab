from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import Plan


class PlanRequiredMixin(LoginRequiredMixin):
    """Protege views por plano (free/basic/premium)."""

    required_plan: str = Plan.BASIC
    insufficient_message = mark_safe(
        'Recurso disponível apenas para os planos Basic e Premium. '
        'Assine um plano em <a href="/pagamentos/planos/">Planos</a> '
        'ou fale pelo <a href="https://wa.me/5511975743767" target="_blank" rel="noopener">'
        "WhatsApp</a>."
    )

    def get_required_plan(self) -> str:
        return self.required_plan

    def handle_no_permission(self):
        # Delega para LoginRequiredMixin quando não autenticado
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        messages.warning(self.request, self.insufficient_message)
        return redirect(reverse("trades:dashboard"))

    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch  # login check
        # Checa plano
        profile = getattr(request.user, "profile", None)
        required = self.get_required_plan()
        if profile is None or not profile.has_plan_at_least(required):
            return self.handle_no_permission()
        return resp(request, *args, **kwargs)


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
                PlanRequiredMixin.insufficient_message,
            )
            return redirect(reverse("trades:dashboard"))

        return _wrapped_view

    return decorator
