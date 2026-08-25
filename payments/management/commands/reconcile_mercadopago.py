"""
Reconcilia as assinaturas locais com o Mercado Pago.

Serve como rede de segurança para tudo o que o webhook possa ter perdido:
notificação que nunca chegou, evento descartado por um bug, indisponibilidade
mais longa que a política de retentativa do MP.

Como todo o processamento passa por `payments.services.plans`, que é
idempotente, reprocessar um evento já aplicado não tem efeito. Isso torna o
comando seguro de rodar quantas vezes quiser.

Uso:
    python manage.py reconcile_mercadopago --dry-run     # só mostra divergências
    python manage.py reconcile_mercadopago               # corrige
    python manage.py reconcile_mercadopago --days 30     # janela maior
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import Subscription
from payments.services.mercadopago import fetch_preapproval
from payments.services.plans import apply_preapproval_event


class Command(BaseCommand):
    help = "Compara as assinaturas locais com o Mercado Pago e corrige divergências."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=15,
            help="Só reconcilia assinaturas atualizadas nos últimos N dias (padrão: 15).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra as divergências sem alterar nada.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Ignora a janela de dias e percorre todas as assinaturas.",
        )

    def handle(self, *args, **options):
        dias = options["days"]
        dry_run = options["dry_run"]

        assinaturas = Subscription.objects.exclude(mp_preapproval_id="").select_related(
            "user__profile"
        )
        if not options["all"]:
            corte = timezone.now() - timedelta(days=dias)
            assinaturas = assinaturas.filter(updated_at__gte=corte)
        assinaturas = assinaturas.order_by("-updated_at")

        total = assinaturas.count()
        self.stdout.write(f"Assinaturas a verificar: {total}")
        if not total:
            return

        divergentes = 0
        corrigidas = 0
        falhas = 0

        for assinatura in assinaturas:
            try:
                remoto = fetch_preapproval(assinatura.mp_preapproval_id)
            except Exception as exc:
                falhas += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {assinatura.mp_preapproval_id}: falha ao consultar o MP ({exc})"
                    )
                )
                continue

            status_remoto = remoto.get("status")
            if status_remoto == assinatura.status:
                continue

            divergentes += 1
            self.stdout.write(
                f"  {assinatura.mp_preapproval_id} (user {assinatura.user_id}): "
                f"local={assinatura.status} remoto={status_remoto}"
            )

            if dry_run:
                continue

            remoto.setdefault("id", assinatura.mp_preapproval_id)
            resultado = apply_preapproval_event(remoto)
            corrigidas += 1
            self.stdout.write(f"      -> {resultado}")

        self.stdout.write("")
        self.stdout.write(f"Divergentes: {divergentes}")
        if falhas:
            self.stdout.write(self.style.WARNING(f"Falhas de consulta: {falhas}"))

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Simulação: nada foi alterado. Rode sem --dry-run para corrigir."
                )
            )
        elif corrigidas:
            self.stdout.write(self.style.SUCCESS(f"Reprocessadas: {corrigidas}"))
        else:
            self.stdout.write(self.style.SUCCESS("Nenhuma divergência encontrada."))
