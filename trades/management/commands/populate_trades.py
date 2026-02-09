"""
Popula o banco com trades fictícios para um usuário.
Uso: python manage.py populate_trades --user=USER
USER pode ser: username, email ou ID (número).
Se --user não for informado, usa o primeiro usuário do banco.
"""
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from trades.models import (
    Trade,
    Market,
    Direction,
    HighTimeFrame,
    Trend,
    PremiumDiscount,
    RegionHTF,
    SMCPanel,
    EntryType,
    Setup,
    Trigger,
    PartialTrade,
    ResultType,
    Currency,
)


def random_choice(choices):
    return random.choice([c[0] for c in choices])


def get_user(identifier):
    """Retorna usuário por username, email ou ID."""
    if identifier is None:
        return User.objects.order_by("id").first()
    identifier = identifier.strip()
    if not identifier:
        return User.objects.order_by("id").first()
    if identifier.isdigit():
        return User.objects.filter(pk=int(identifier)).first()
    return (
        User.objects.filter(username=identifier).first()
        or User.objects.filter(email__iexact=identifier).first()
    )


def generate_trades(user, count=40):
    symbols = [
        ("WINFUT", Market.INDICES),
        ("DOLFUT", Market.DOLLAR),
        ("VALE3", Market.STOCKS),
        ("PETR4", Market.STOCKS),
        ("NVDA", Market.STOCKS),
    ]
    for _ in range(count):
        symbol, market = random.choice(symbols)
        executed_at = timezone.now() - timezone.timedelta(
            days=random.randint(0, 29),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        direction = random.choice([Direction.BUY, Direction.SELL])
        htf = random_choice(HighTimeFrame.choices)
        trend = random_choice(Trend.choices)
        premium = random_choice(PremiumDiscount.choices)
        region = random_choice(RegionHTF.choices)
        entry_type = random_choice(EntryType.choices)
        setup = random_choice(Setup.choices)
        trigger = random_choice(Trigger.choices)
        partial = random_choice(PartialTrade.choices)
        smc_panel = random_choice(SMCPanel.choices)
        result = random.choices(
            [ResultType.GAIN, ResultType.LOSS, ResultType.BREAK_EVEN],
            weights=[0.45, 0.35, 0.20],
        )[0]
        # Ganho técnico na mesma unidade que resultado (reais), para Result/ Técnico fazer sentido
        if result == ResultType.GAIN:
            profit = Decimal(random.randint(50, 400))
            # technical = quanto o mercado oferecia; entre 80% e 120% do profit para % razoável
            ratio = Decimal(str(round(random.uniform(0.80, 1.20), 2)))
            technical = (profit * ratio).quantize(Decimal("0.01"))
        elif result == ResultType.LOSS:
            profit = Decimal(-random.randint(40, 350))
            ratio = Decimal(str(round(random.uniform(0.80, 1.20), 2)))
            technical = (profit * ratio).quantize(Decimal("0.01"))
        else:
            profit = Decimal("0")
            technical = Decimal("0.00")
        quantity = Decimal(random.randint(1, 5))
        base_price = (
            Decimal(random.randint(150, 300))
            if market == Market.STOCKS
            else Decimal(random.randint(1000, 2000))
        )
        target_price = base_price + Decimal(random.randint(5, 25))
        stop_price = base_price - Decimal(random.randint(5, 20))
        currency = (
            Currency.USD
            if market in {Market.DOLLAR, Market.CRYPTO, Market.FOREX}
            else Currency.BRL
        )
        is_public = random.random() < 0.6
        display_anon = True if not is_public else (random.random() < 0.5)
        Trade.objects.create(
            user=user,
            executed_at=executed_at,
            symbol=symbol,
            market=market,
            direction=direction,
            quantity=quantity,
            high_time_frame=htf,
            trend=trend,
            smc_panel=smc_panel,
            premium_discount=premium,
            region_htf=region,
            entry_type=entry_type,
            setup=setup,
            trigger=trigger,
            target_price=target_price,
            stop_price=stop_price,
            partial_trade=partial,
            result_type=result,
            currency=currency,
            profit_amount=profit,
            technical_gain=technical,
            is_public=is_public,
            display_as_anonymous=display_anon,
            notes="Trade de teste gerado automaticamente.",
        )


class Command(BaseCommand):
    help = "Popula trades fictícios para um usuário (--user=username|email|id). Sem --user usa o primeiro usuário."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Username, email ou ID do usuário. Se omitido, usa o primeiro usuário.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=40,
            help="Quantidade de trades a gerar (padrão: 40).",
        )
        parser.add_argument(
            "--no-reset",
            action="store_true",
            help="Não apaga os trades existentes do usuário nem reseta o saldo.",
        )

    def handle(self, *args, **options):
        user_ident = options.get("user")
        count = max(1, options.get("count", 40))
        no_reset = options.get("no_reset", False)

        user = get_user(user_ident)
        if user is None:
            self.stderr.write(
                self.style.ERROR(
                    f"Nenhum usuário encontrado para: {user_ident or '(primeiro)'}"
                )
            )
            return
        if not no_reset:
            profile = user.profile
            profile.reset_balance(Decimal("10000"))
            deleted, _ = Trade.objects.filter(user=user).delete()
            self.stdout.write(
                f"Saldo resetado para R$ 10.000 e {deleted} trade(s) removido(s)."
            )
        generate_trades(user, count=count)
        total = Trade.objects.filter(user=user).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Foram gerados {total} trades para o usuário {user.username} (id={user.pk})."
            )
        )
