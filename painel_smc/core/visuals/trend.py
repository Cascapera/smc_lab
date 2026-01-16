# Plota a tendência temporal do sentimento com base na soma acumulada
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_trend_series(scores_path: Path, *, since: datetime | None = None) -> pd.Series:
    """Retorna a série crua da linha 'Soma Acumulada' (opcionalmente desde um horário)."""
    return _load_cumulative_series(scores_path, since=since)


def _load_cumulative_series(scores_path: Path, since: datetime | None = None) -> pd.Series:
    """Extrai os valores da linha 'Soma Acumulada' como série temporal float."""
    df = pd.read_csv(scores_path)
    if "Ativo" not in df.columns:
        raise ValueError("Coluna 'Ativo' ausente em historico_scores.csv")

    df = df.set_index("Ativo")
    if "Soma Acumulada" not in df.index:
        raise ValueError("Linha 'Soma Acumulada' não encontrada em historico_scores.csv")

    series = df.loc["Soma Acumulada"]

    if since is not None:
        timestamps = pd.to_datetime(series.index, errors="coerce")
        series = series[timestamps >= since]
        if series.empty:
            raise ValueError("Nenhum dado de tendência após o início da sessão.")

    return series.apply(lambda value: float(str(value).replace("+", "")))


def render_sentiment_trend(
    scores_path: Path,
    output_path: Optional[Path] = None,
    *,
    ax: Optional[plt.Axes] = None,
    max_points: int = 60,
    since: datetime | None = None,
) -> plt.Figure:
    """Gera gráfico de linha mostrando a evolução da soma acumulada das variações."""
    cumulative = _load_cumulative_series(scores_path, since=since)
    if len(cumulative) > max_points:
        cumulative = cumulative.iloc[-max_points:]

    timestamps = pd.to_datetime(cumulative.index.tolist(), errors="coerce")
    time_labels = [
        moment.strftime("%H:%M") if pd.notna(moment) else str(raw) for moment, raw in zip(timestamps, cumulative.index)
    ]
    values = cumulative.values.astype(float)

    created_fig = False
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        created_fig = True
    else:
        fig = ax.figure
        ax.clear()

    fig.patch.set_facecolor("#161616")
    ax.set_facecolor("#161616")

    x = range(len(time_labels))
    ax.plot(x, values, color="#f0c330", linewidth=2.5)

    # Faixas fixas de 2% com extensão da última cor (positivo e negativo)
    band_step = 0.02  # 2%
    max_abs = float(max(np.abs(values).max(), band_step, 0.04))
    bands = np.arange(0, max_abs + band_step, band_step)
    if bands[-1] < max_abs:
        bands = np.append(bands, bands[-1] + band_step)

    greens = [plt.cm.Greens(0.3 + 0.4 * (i / max(len(bands) - 2, 1))) for i in range(len(bands) - 1)]
    reds = [plt.cm.Reds(0.3 + 0.4 * (i / max(len(bands) - 2, 1))) for i in range(len(bands) - 1)]
    for i in range(len(bands) - 1):
        y0, y1 = bands[i], bands[i + 1]
        ax.axhspan(y0, y1, facecolor=greens[i], alpha=0.22, zorder=0)
        ax.axhspan(-y1, -y0, facecolor=reds[i], alpha=0.22, zorder=0)

    span = max_abs
    lastg = greens[-1] if greens else "#0f0"
    lastr = reds[-1] if reds else "#f00"
    ax.axhspan(bands[-1], bands[-1] + span, facecolor=lastg, alpha=0.22, zorder=0)
    ax.axhspan(-bands[-1] - span, -bands[-1], facecolor=lastr, alpha=0.22, zorder=0)

    # Linha de referência e limites simétricos com folga
    ax.axhline(0, color="#888888", linewidth=1.1, linestyle="--", alpha=0.9)
    padding = span * 0.3
    ax.set_ylim(-span - padding, span + padding)

    # Eixo X/Y
    ax.set_xticks([])
    ax.set_yticks([])
    ax.yaxis.grid(False)
    ax.tick_params(axis="y", length=0, labelleft=False)
    ax.tick_params(axis="x", length=0, labelbottom=False)

    ax.set_title("")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#444444")

    if created_fig:
        fig.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())

    if created_fig:
        plt.close(fig)

    return fig

