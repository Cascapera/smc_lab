from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField("e-mail", unique=True)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self) -> str:
        return self.get_full_name() or self.username


class ExperienceLevel(models.TextChoices):
    BEGINNER = "beginner", "Iniciante"
    INTERMEDIATE = "intermediate", "Intermediário"
    ADVANCED = "advanced", "Avançado"


class PrimaryMarket(models.TextChoices):
    STOCKS = "stocks", "Ações"
    INDEX_FUTURES = "index_futures", "Índice Futuro"
    DOLLAR_FUTURES = "dollar_futures", "Dólar Futuro"
    CRYPTO = "crypto", "Criptoativos"
    OTHER = "other", "Outros"


class TradingStyle(models.TextChoices):
    DAY_TRADE = "day_trade", "Day Trade"
    SWING_TRADE = "swing_trade", "Swing Trade"
    POSITION = "position", "Position"
    INVESTOR = "investor", "Investidor"


class Plan(models.TextChoices):
    FREE = "free", "Free"
    BASIC = "basic", "Basic"
    PREMIUM = "premium", "Premium"
    PREMIUM_PLUS = "premium_plus", "Premium+"


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone = models.CharField("telefone", max_length=20, blank=True)
    document_id = models.CharField("documento (CPF/CNPJ)", max_length=20, blank=True)
    country = models.CharField("país", max_length=50, default="BR")
    state = models.CharField("estado", max_length=50, blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    zipcode = models.CharField("CEP", max_length=20, blank=True)
    address_line1 = models.CharField("endereço", max_length=200, blank=True)
    address_line2 = models.CharField("complemento", max_length=200, blank=True)

    experience_level = models.CharField(
        "nível de experiência",
        max_length=20,
        choices=ExperienceLevel.choices,
        default=ExperienceLevel.BEGINNER,
    )
    primary_market = models.CharField(
        "mercado principal",
        max_length=20,
        choices=PrimaryMarket.choices,
        default=PrimaryMarket.INDEX_FUTURES,
    )
    trading_style = models.CharField(
        "estilo de operação",
        max_length=20,
        choices=TradingStyle.choices,
        default=TradingStyle.DAY_TRADE,
    )
    broker = models.CharField("corretora", max_length=100, blank=True)
    timezone = models.CharField(
        "fuso horário",
        max_length=50,
        default="America/Sao_Paulo",
    )

    email_opt_in = models.BooleanField("aceita receber e-mails?", default=True)
    terms_accepted = models.BooleanField("aceitou os termos?", default=False)
    terms_accepted_at = models.DateTimeField(
        "aceito em",
        blank=True,
        null=True,
    )
    privacy_accepted = models.BooleanField(
        "aceitou política de privacidade?", default=False
    )
    privacy_accepted_at = models.DateTimeField(
        "aceitado em",
        blank=True,
        null=True,
    )

    referral_source = models.CharField("como conheceu", max_length=100, blank=True)
    initial_balance = models.DecimalField(
        "saldo inicial",
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    current_balance = models.DecimalField(
        "saldo atual",
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    plan = models.CharField(
        "plano",
        max_length=12,
        choices=Plan.choices,
        default=Plan.FREE,
    )
    plan_expires_at = models.DateTimeField(
        "plano expira em",
        blank=True,
        null=True,
        help_text="Defina para expirará automaticamente no dia especificado.",
    )
    last_reset_at = models.DateTimeField(
        "último reset",
        blank=True,
        null=True,
    )
    discord_user_id = models.CharField(
        "discord id",
        max_length=30,
        blank=True,
    )
    discord_username = models.CharField(
        "discord usuário",
        max_length=120,
        blank=True,
    )
    discord_connected_at = models.DateTimeField(
        "discord conectado em",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfis"

    def __str__(self) -> str:
        return f"Perfil de {self.user}"

    def reset_balance(self, amount: Decimal) -> None:
        """Define novo saldo inicial e zera o acumulado a partir deste valor."""
        self.initial_balance = amount
        self.current_balance = amount
        self.last_reset_at = timezone.now()
        self.save(
            update_fields=["initial_balance", "current_balance", "last_reset_at"]
        )

    def active_plan(self) -> str:
        """Retorna o plano vigente considerando data de expiração."""
        if self.plan_expires_at and self.plan_expires_at < timezone.now():
            return Plan.FREE
        return self.plan

    def has_plan_at_least(self, required_plan: str) -> bool:
        rank = {
            Plan.FREE: 0,
            Plan.BASIC: 1,
            Plan.PREMIUM: 2,
            Plan.PREMIUM_PLUS: 3,
        }
        return rank[self.active_plan()] >= rank[required_plan]
