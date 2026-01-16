# Gera o gauge de sentimento em formato semicircular (estilo velocímetro)
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, Wedge


@dataclass(frozen=True)
class GaugeConfig:
    """Configuração central do gauge."""

    min_score: float = -24.0
    max_score: float = 24.0
    step: float = 6.0
    pointer_color: str = "#CCFF00"  # amarelo fluorescente
    radius: float = 1.0
    inner_radius: float = 0.55

    def clamp_score(self, score: float) -> float:
        """Limita o score dentro do intervalo esperado."""
        return float(np.clip(score, self.min_score, self.max_score))

    def bucket_index(self, score: float) -> int:
        """Converte o score em um índice de faixa (0-7)."""
        clamped = self.clamp_score(score)
        raw_index = int((clamped - self.min_score) // self.step)
        max_index = int((self.max_score - self.min_score) // self.step) - 1
        return int(np.clip(raw_index, 0, max_index))

    def bucket_angles(self) -> np.ndarray:
        """Divide a semi-curva em segmentos iguais."""
        buckets = int((self.max_score - self.min_score) / self.step)
        return np.linspace(180, 0, buckets + 1)

    def pointer_angle(self, score: float) -> float:
        """Transforma o score em ângulo dentro do semi-círculo."""
        clamped = self.clamp_score(score)
        return np.interp(clamped, [self.min_score, self.max_score], [180, 0])


def _segment_colors() -> Iterable[str]:
    """Define cores das faixas (pessimista → neutro → otimista)."""
    return (
        "#7a0606",
        "#a61919",
        "#c43d3d",
        "#707070",
        "#5f6f5f",
        "#3c8c40",
        "#1f8c1f",
        "#0f6610",
    )


def _label_for_index(index: int) -> Tuple[str, str]:
    """Define texto principal e subtítulo de acordo com a faixa."""
    if index <= 2:
        return "Mercado Pessimista", "Pressão vendedora prevalece"
    if index >= 5:
        return "Mercado Otimista", "Fluxo comprador dominante"
    return "Mercado Neutro", "Equilíbrio entre compra e venda"


def load_latest_score(scores_path: Path, *, since: datetime | None = None) -> Tuple[float, str]:
    """Obtém o score agregado mais recente e o rótulo da medição (opcionalmente desde um horário)."""
    if not scores_path.exists():
        raise FileNotFoundError(f"Arquivo '{scores_path}' não encontrado.")

    df = pd.read_csv(scores_path)
    if "Ativo" not in df.columns:
        raise ValueError("Coluna 'Ativo' ausente em historico_scores.csv")

    if "Soma" not in df["Ativo"].values:
        raise ValueError("Linha 'Soma' não encontrada em historico_scores.csv")

    df = df.set_index("Ativo")
    sum_row = df.loc["Soma"].astype(float)

    if since is not None:
        timestamps = pd.to_datetime(sum_row.index, errors="coerce")
        filtered = sum_row[timestamps >= since]
        if filtered.empty:
            raise ValueError("Nenhum score disponível após o início da sessão.")
        sum_row = filtered

    latest_label = sum_row.index[-1]
    latest_score = float(sum_row.iloc[-1])
    return latest_score, latest_label


def render_market_sentiment_gauge(
    score: float,
    output_path: Path | None = None,
    cfg: GaugeConfig | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Cria o gauge em formato de velocímetro (salvando em arquivo ou desenhando em um Axes)."""
    cfg = cfg or GaugeConfig()
    angles = cfg.bucket_angles()
    pointer_angle = cfg.pointer_angle(score)

    created_fig = False
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 5))
        created_fig = True
    else:
        fig = ax.figure
        ax.clear()

    ax.set_aspect("equal")
    ax.axis("off")

    # Fundo
    fig.patch.set_facecolor("#161616")
    ax.set_facecolor("#161616")

    # Semicírculo principal
    for start, end, color in zip(angles[:-1], angles[1:], _segment_colors()):
        wedge = Wedge(
            center=(0, 0),
            r=cfg.radius,
            theta1=end,
            theta2=start,
            width=cfg.radius - cfg.inner_radius,
            facecolor=color,
            edgecolor="#111111",
            linewidth=1.2,
        )
        ax.add_patch(wedge)

    # Base inferior
    base_circle = Circle((0, 0), cfg.inner_radius - 0.05, facecolor="#101010", edgecolor="#0c0c0c", linewidth=2)
    ax.add_patch(base_circle)

    # Ponteiro
    pointer_length = cfg.radius * 0.92
    pointer_width = 0.06
    angle_rad = np.deg2rad(pointer_angle)
    pointer_x = pointer_length * np.cos(angle_rad)
    pointer_y = pointer_length * np.sin(angle_rad)
    ax.plot([0, pointer_x], [0, pointer_y], color=cfg.pointer_color, linewidth=6, solid_capstyle="round", zorder=5)

    # Base do ponteiro
    hub = Circle((0, 0), 0.09, facecolor=cfg.pointer_color, edgecolor="#242424", linewidth=1.5, zorder=6)
    ax.add_patch(hub)

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-0.1, 1.15)

    if created_fig:
        fig.tight_layout()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())

    if created_fig:
        plt.close(fig)

    return fig

