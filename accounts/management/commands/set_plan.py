from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Plan, Profile, User


class Command(BaseCommand):
    help = "Define o plano de um usuário e a data de expiração (opcional)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Username do usuário")
        parser.add_argument(
            "--plan",
            required=True,
            choices=[Plan.FREE, Plan.BASIC, Plan.PREMIUM],
            help="Plano a aplicar (free/basic/premium)",
        )
        parser.add_argument(
            "--expires",
            help="Data de expiração no formato YYYY-MM-DD (opcional).",
        )

    def handle(self, *args, **options):
        username = options["username"]
        plan = options["plan"]
        expires = options.get("expires")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Usuário '{username}' não encontrado.") from exc

        profile, _ = Profile.objects.get_or_create(user=user)

        expires_at = None
        if expires:
            try:
                expires_date = datetime.datetime.strptime(expires, "%Y-%m-%d")
            except ValueError as exc:
                raise CommandError("Use data no formato YYYY-MM-DD em --expires.") from exc
            expires_at = timezone.make_aware(expires_date, timezone.get_current_timezone())

        profile.plan = plan
        profile.plan_expires_at = expires_at
        profile.save(update_fields=["plan", "plan_expires_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Plano de {user.username} definido para {plan}"
                + (f" até {expires_at.date()}" if expires_at else "")
            )
        )
