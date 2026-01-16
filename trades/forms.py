from __future__ import annotations

from django import forms

from .models import Trade


class TradeForm(forms.ModelForm):
    executed_at = forms.DateTimeField(
        label="Data e hora da operação",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = Trade
        fields = [
            "executed_at",
            "symbol",
            "market",
            "direction",
            "quantity",
            "high_time_frame",
            "trend",
            "smc_panel",
            "premium_discount",
            "region_htf",
            "entry_type",
            "setup",
            "trigger",
            "target_price",
            "stop_price",
            "partial_trade",
            "result_type",
            "currency",
            "profit_amount",
            "technical_gain",
            "is_public",
            "display_as_anonymous",
            "screenshot",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Força o select de Painel SMC a iniciar em branco, para não manter o valor anterior após refresh.
        smc_field = self.fields.get("smc_panel")
        if smc_field:
            smc_field.choices = [("", "Selecione")] + list(smc_field.choices)
            smc_field.initial = ""

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_public") is False:
            cleaned_data["display_as_anonymous"] = True
        return cleaned_data

