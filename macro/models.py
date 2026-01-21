from django.db import models


class SourceChoices(models.TextChoices):
    INVESTING = "investing", "Investing"
    TRADINGVIEW = "tradingview", "TradingView"


class MacroAsset(models.Model):
    name = models.CharField(max_length=120)
    url = models.URLField()
    value_base = models.FloatField()
    source_key = models.CharField(max_length=20, choices=SourceChoices.choices)
    category = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["active"]),
            models.Index(fields=["source_key"]),
        ]

    def __str__(self) -> str:
        return self.name


class MacroVariation(models.Model):
    asset = models.ForeignKey(
        MacroAsset, on_delete=models.CASCADE, related_name="variations"
    )
    measurement_time = models.DateTimeField(db_index=True)
    variation_text = models.CharField(max_length=50, null=True, blank=True)
    variation_decimal = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=30)
    block_reason = models.CharField(max_length=120, blank=True)
    source_excerpt = models.TextField(blank=True)
    market_phase = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-measurement_time", "asset__name"]
        unique_together = ("asset", "measurement_time")
        indexes = [
            models.Index(fields=["measurement_time"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.asset.name} @ {self.measurement_time:%Y-%m-%d %H:%M}"


class MacroScore(models.Model):
    measurement_time = models.DateTimeField(unique=True)
    total_score = models.IntegerField()
    variation_sum = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-measurement_time"]
        indexes = [models.Index(fields=["measurement_time"])]

    def __str__(self) -> str:
        return f"Score {self.total_score} @ {self.measurement_time:%Y-%m-%d %H:%M}"
