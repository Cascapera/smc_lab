"""Admin site customizado com resumo no dashboard (assinantes e vendas)."""

from __future__ import annotations

from django.contrib.admin import AdminSite
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group


class SMCAdminSite(AdminSite):
    site_header = "SMC Lab"
    site_title = "Admin"
    index_title = "Painel"

    def index(self, request, extra_context=None):
        """Resumo do dashboard, cada bloco atrás da sua permissão.

        Antes o contexto era montado para qualquer `is_staff`: um usuário com
        acesso só a `trades` via os 20 últimos pagamentos, com valor e e-mail
        dos clientes.
        """
        extra_context = extra_context or {}
        from django.db.models import Q
        from django.utils import timezone

        from accounts.models import Plan, Profile
        from payments.models import Payment, PaymentStatus

        if request.user.has_perm("accounts.view_profile"):
            now = timezone.now()
            extra_context["active_subscribers_count"] = (
                Profile.objects.exclude(plan=Plan.FREE)
                .filter(Q(plan_expires_at__isnull=True) | Q(plan_expires_at__gt=now))
                .count()
            )
            extra_context["pode_ver_assinantes"] = True

        if request.user.has_perm("payments.view_payment"):
            extra_context["recent_sales"] = list(
                Payment.objects.filter(status=PaymentStatus.APPROVED)
                .select_related("user")
                .order_by("-created_at")[:20]
            )
            extra_context["pode_ver_vendas"] = True

        return super().index(request, extra_context)


admin_site = SMCAdminSite(name="admin")

admin_site.register(Group, GroupAdmin)
