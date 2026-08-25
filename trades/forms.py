from __future__ import annotations

from django import forms

from .models import Direction, ResultType, Trade


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

    def clean_symbol(self) -> str:
        """Armazena ticker sempre em maiúsculas."""
        symbol = self.cleaned_data.get("symbol", "")
        return (symbol or "").strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_public") is False:
            cleaned_data["display_as_anonymous"] = True
        self.avisos = self._checar_coerencia(cleaned_data)
        return cleaned_data

    def _checar_coerencia(self, dados: dict) -> list[str]:
        """
        Detecta combinações contraditórias, sem impedir o registro.

        Por que importa: os relatórios usam `result_type` para o win rate, mas o
        SINAL de `profit_amount` para streaks, payoff e profit factor. Quando os
        dois discordam, as duas métricas deixam de ser comparáveis entre si — e
        nada avisava o usuário.

        Aviso e não bloqueio porque pode haver registro legítimo que eu não
        conheço (parcial, ajuste de corretora). Se um dia ficar claro que não há,
        vira validação.
        """
        avisos: list[str] = []
        resultado = dados.get("result_type")
        lucro = dados.get("profit_amount")
        direcao = dados.get("direction")
        stop = dados.get("stop_price")
        alvo = dados.get("target_price")

        if resultado and lucro is not None:
            if resultado == ResultType.GAIN and lucro < 0:
                avisos.append("Marcado como ganho, mas o resultado financeiro é negativo.")
            elif resultado == ResultType.LOSS and lucro > 0:
                avisos.append("Marcado como perda, mas o resultado financeiro é positivo.")
            elif resultado == ResultType.BREAK_EVEN and lucro != 0:
                avisos.append("Marcado como empate, mas o resultado financeiro não é zero.")

        if direcao and stop is not None and alvo is not None:
            if direcao == Direction.BUY and stop > alvo:
                avisos.append("Em compra, o stop está acima do alvo.")
            elif direcao == Direction.SELL and stop < alvo:
                avisos.append("Em venda, o stop está abaixo do alvo.")

        return avisos
