"""Comando para fazer downgrade manual de planos expirados."""

from django.core.management.base import BaseCommand

from accounts.tasks import downgrade_expired_plans


class Command(BaseCommand):
    help = "Atualiza perfis com plano expirado para Free (igual à task Celery)."

    def handle(self, *args, **options):
        count = downgrade_expired_plans()
        self.stdout.write(
            self.style.SUCCESS(f"{count} perfil(is) atualizado(s) para Free.")
        )
