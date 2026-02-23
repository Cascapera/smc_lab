import random
from decimal import Decimal

from django.utils import timezone

from accounts.models import User
from trades.models import (
    Currency,
    Direction,
    EntryType,
    HighTimeFrame,
    Market,
    PartialTrade,
    PremiumDiscount,
    RegionHTF,
    ResultType,
    Setup,
    Trade,
    Trend,
    Trigger,
)

user = User.objects.order_by("id").first()
if user is None:
    print("Nenhum usuÃ¡rio disponÃ­vel.")
    raise SystemExit

profile = user.profile
profile.reset_balance(Decimal("10000"))

Trade.objects.filter(user=user).delete()

symbols = [
    ("WINFUT", Market.INDICES),
    ("DOLFUT", Market.DOLLAR),
    ("VALE3", Market.STOCKS),
    ("PETR4", Market.STOCKS),
    ("NVDA", Market.STOCKS),
]


def random_choice(choices):
    return random.choice([choice[0] for choice in choices])


for _ in range(40):
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

    result = random.choices(
        [ResultType.GAIN, ResultType.LOSS, ResultType.BREAK_EVEN],
        weights=[0.45, 0.35, 0.20],
    )[0]

    # Ganho técnico na mesma unidade que resultado (reais), para Result/ Técnico fazer sentido
    if result == ResultType.GAIN:
        profit = Decimal(random.randint(50, 400))
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
        Currency.USD if market in {Market.DOLLAR, Market.CRYPTO, Market.FOREX} else Currency.BRL
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

print(
    f"Foram gerados {Trade.objects.filter(user=user).count()} trades para o usuÃ¡rio {user.username}."
)
