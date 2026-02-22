from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

from .validators import validate_image_file_size


class Market(models.TextChoices):
    STOCKS = "stocks", "Ações"
    INDICES = "indices", "Índices"
    DOLLAR = "dollar", "Dólar"
    CRYPTO = "crypto", "Cripto"
    FOREX = "forex", "Forex"


class Direction(models.TextChoices):
    BUY = "buy", "Compra"
    SELL = "sell", "Venda"


class HighTimeFrame(models.TextChoices):
    M5 = "5", "5 min"
    M15 = "15", "15 min"
    H1 = "60", "60 min"
    H4 = "240", "240 min"


class Trend(models.TextChoices):
    BULLISH = "bullish", "A favor"
    RANGE = "range", "Lateral"
    BEARISH = "bearish", "Contra"


class PremiumDiscount(models.TextChoices):
    SELL_PREMIUM = "sell_premium", "Venda prêmio"
    SELL_DISCOUNT = "sell_discount", "Venda desconto"
    BUY_PREMIUM = "buy_premium", "Compra prêmio"
    BUY_DISCOUNT = "buy_discount", "Compra desconto"


class RegionHTF(models.TextChoices):
    PRIMARY = "primary", "Primária"
    SECONDARY = "secondary", "Secundária"
    NONE = "none", "N/D"


class SMCPanel(models.TextChoices):
    OPTIMISTIC = "optimistic", "A favor"
    PESSIMISTIC = "pessimistic", "Contra"
    NEUTRAL = "neutral", "Neutro"


class EntryType(models.TextChoices):
    ANTICIPATED = "anticipated", "Antecipado"
    CONFIRMED = "confirmed", "Confirmado"
    LATERAL = "lateral", "Lateral"


class Setup(models.TextChoices):
    FLIP = "flip", "Flip"
    CHOCH = "choch", "Choch"
    LIQUIDITY = "liquidity", "Liquidity"
    PD = "pd", "PD"
    FVG = "fvg", "FVG"
    TOP_FAILURE = "top_failure", "Falha de topo"
    BOTTOM_FAILURE = "bottom_failure", "Falha de fundo"
    CONTINUATION = "continuation", "Continuação"
    DOUBLE_TOP = "double_top", "Topo duplo"
    DOUBLE_BOTTOM = "double_bottom", "Fundo duplo"
    NONE = "none", "N/D"
    WEDGE = "wedge", "Cunha"



class Trigger(models.TextChoices):
    REGION = "region", "Região"
    PASSAGEM = "passagem", "Passagem"
    MARTELO_BF = "martelo_bf", "Martelo + BF"
    FFFD = "fffd", "FFFD"
    PADRAO = "padrao", "Padrão"
    NONE = "none", "N/D"
    ROCADINHA = "rocadinha", "Roçadinha"
    BARRA_IGNORADA = "barra_ignorada", "Barra ignorada"
    GIFT = "gift", "Gift"


class PartialTrade(models.TextChoices):
    YES_POS = "yes_pos", "Sim +5x1"
    NO_DONE = "no_done", "Não fiz"
    YES_NEG = "yes_neg", "Sim -5x1"
    NOT_AVAILABLE = "not_available", "Sem parcial"


class ResultType(models.TextChoices):
    GAIN = "gain", "Gain"
    LOSS = "loss", "Loss"
    BREAK_EVEN = "break_even", "Break even"


class Currency(models.TextChoices):
    BRL = "BRL", "Real"
    USD = "USD", "Dólar"
    EUR = "EUR", "Euro"
    


class Trade(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    executed_at = models.DateTimeField("executado em")
    symbol = models.CharField("ticker", max_length=20)
    market = models.CharField(
        "mercado",
        max_length=20,
        choices=Market.choices,
    )
    direction = models.CharField(
        "direção",
        max_length=10,
        choices=Direction.choices,
    )
    quantity = models.DecimalField(
        "quantidade",
        max_digits=16,
        decimal_places=8,
        validators=[MinValueValidator(Decimal("0.00000001"))],
    )
    high_time_frame = models.CharField(
        "HTF",
        max_length=3,
        choices=HighTimeFrame.choices,
    )
    trend = models.CharField(
        "tendência",
        max_length=10,
        choices=Trend.choices,
    )
    smc_panel = models.CharField(
        "Painel SMC",
        max_length=15,
        choices=SMCPanel.choices,
        default=SMCPanel.NEUTRAL,
    )
    premium_discount = models.CharField(
        "prêmio/desconto",
        max_length=20,
        choices=PremiumDiscount.choices,
    )
    region_htf = models.CharField(
        "região HTF",
        max_length=15,
        choices=RegionHTF.choices,
    )
    entry_type = models.CharField(
        "tipo de entrada",
        max_length=12,
        choices=EntryType.choices,
    )
    setup = models.CharField(
        "setup",
        max_length=15,
        choices=Setup.choices,
    )
    trigger = models.CharField(
        "gatilho",
        max_length=20,
        choices=Trigger.choices,
    )
    target_price = models.DecimalField(
        "alvo",
        max_digits=16,
        decimal_places=5,
    )
    stop_price = models.DecimalField(
        "stop",
        max_digits=16,
        decimal_places=5,
    )
    partial_trade = models.CharField(
        "parcial",
        max_length=20,
        choices=PartialTrade.choices,
    )
    result_type = models.CharField(
        "resultado",
        max_length=12,
        choices=ResultType.choices,
    )
    currency = models.CharField(
        "moeda",
        max_length=5,
        choices=Currency.choices,
        default=Currency.BRL,
    )
    profit_amount = models.DecimalField(
        "resultado financeiro",
        max_digits=16,
        decimal_places=2,
    )
    technical_gain = models.DecimalField(
        "ganho técnico",
        max_digits=16,
        decimal_places=2,
    )
    is_public = models.BooleanField(
        "exibir publicamente?",
        default=False,
        help_text="Permite mostrar esta operação no mural compartilhado.",
    )
    display_as_anonymous = models.BooleanField(
        "exibir como anônimo?",
        default=True,
        help_text="Se público, mostra o trader como 'Anônimo' nas visualizações.",
    )
    screenshot = models.ImageField(
        "captura",
        upload_to="trades/screenshots/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png"]),
            validate_image_file_size,
        ],
        help_text="Envie uma imagem PNG ou JPEG com até 1 MB.",
    )
    notes = models.TextField("observações", blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ("-executed_at", "-id")
        verbose_name = "trade"
        verbose_name_plural = "trades"

    def __str__(self) -> str:
        return f"{self.symbol} ({self.get_direction_display()}) - {self.executed_at:%Y-%m-%d %H:%M}"


class AIAnalyticsRun(models.Model):
    """
    Registro de cada execução de análise por IA (limite 1x por semana).
    Só é criado quando há chamada real à LLM. result guarda a resposta da IA.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_analytics_runs",
    )
    requested_at = models.DateTimeField("solicitado em", auto_now_add=True)
    result = models.TextField("resultado da análise", blank=True)

    class Meta:
        ordering = ("-requested_at",)
        verbose_name = "execução análise IA"
        verbose_name_plural = "execuções análise IA"

    def __str__(self) -> str:
        return f"Análise IA – {self.user} em {self.requested_at:%Y-%m-%d %H:%M}"


class GlobalAIAnalyticsRun(models.Model):
    """
    Registro de cada execução de análise por IA do dashboard global.
    Usado pela equipe para analisar métricas agregadas de todos os usuários.
    """

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="global_ai_analytics_runs",
    )
    requested_at = models.DateTimeField("solicitado em", auto_now_add=True)
    result = models.TextField("resultado da análise", blank=True)

    class Meta:
        ordering = ("-requested_at",)
        verbose_name = "execução análise IA global"
        verbose_name_plural = "execuções análise IA global"

    def __str__(self) -> str:
        return f"Análise IA Global em {self.requested_at:%Y-%m-%d %H:%M}"
