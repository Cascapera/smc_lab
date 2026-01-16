# Painel ao vivo para exibir gauge e tendência em tempo real
import sys
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import FancyBboxPatch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import config  # noqa: E402
from core.services import events  # noqa: E402
from core.visuals import (  # noqa: E402
    load_latest_score,
    load_latest_variation,
    render_market_sentiment_gauge,
    render_sentiment_trend,
)

REFRESH_INTERVAL_SECONDS = 2  # checagem leve para reagir ao evento sem polling pesado
FALLBACK_INTERVAL_SECONDS = max(10, config.TARGET_INTERVAL_MINUTES * 60)
POSITIVE_COLOR = "#4caf50"
NEGATIVE_COLOR = "#ff5252"
NEUTRAL_COLOR = "#d0d0d0"

# Controle de última atualização para evitar renderizações desnecessárias
_last_refresh_monotonic = 0.0
SESSION_START = datetime.now()

def _wrap_with_card(ax: plt.Axes) -> None:
    """Adiciona moldura arredondada e sombra leve ao Axes."""
    trans = ax.transAxes
    shadow = FancyBboxPatch(
        (-0.04, -0.04),
        1.08,
        1.08,
        transform=trans,
        boxstyle="round,pad=0.08",
        linewidth=0,
        facecolor="black",
        alpha=0.20,
        zorder=-2,
    )
    body = FancyBboxPatch(
        (-0.02, -0.02),
        1.04,
        1.04,
        transform=trans,
        boxstyle="round,pad=0.10",
        linewidth=1.0,
        edgecolor="#444444",
        facecolor="#161616",
        alpha=0.95,
        zorder=-1,
    )
    ax.add_patch(shadow)
    ax.add_patch(body)


def _format_ticker_text(ticker: str, text_value: str | None, decimal_value: float | None) -> tuple[str, str]:
    """Monta o texto e decide a cor conforme o sinal da variação."""
    if text_value is None or decimal_value is None:
        return f"{ticker}: N/D", NEUTRAL_COLOR

    if decimal_value > 0:
        color = POSITIVE_COLOR
    elif decimal_value < 0:
        color = NEGATIVE_COLOR
    else:
        color = NEUTRAL_COLOR

    return f"{ticker}: {text_value}", color


def _render_ticker_box(ax: plt.Axes, text: str, color: str) -> None:
    """Limpa o Axes e escreve o texto do ticker centralizado."""
    ax.clear()
    ax.set_facecolor("#111111")
    ax.axis("off")
    ax.text(0.5, 0.5, text, ha="center", va="center", color=color, fontsize=22, fontweight="bold", transform=ax.transAxes)


def _update_axes(_, ax_gauge, ax_trend, ax_ewz, ax_dxy):
    """Atualiza ambas as visualizações a partir dos dados mais recentes."""
    global _last_refresh_monotonic

    now = time.monotonic()
    has_signal = events.consume_data_ready()
    elapsed = now - _last_refresh_monotonic

    if not has_signal and elapsed < FALLBACK_INTERVAL_SECONDS:
        return  # evita atualizações desnecessárias

    _last_refresh_monotonic = now

    scores_path = config.SCORES_PATH
    if not scores_path.exists():
        for ax in (ax_gauge, ax_trend):
            ax.clear()
            ax.text(
                0.5,
                0.5,
                "Aguardando dados...",
                ha="center",
                va="center",
                color="#dddddd",
                fontsize=14,
            )
            ax.axis("off")
        _render_ticker_box(ax_ewz, "EWZ: N/D", NEUTRAL_COLOR)
        _render_ticker_box(ax_dxy, "DXY: N/D", NEUTRAL_COLOR)
        return

    try:
        score, _ = load_latest_score(scores_path, since=SESSION_START)
        render_market_sentiment_gauge(score, ax=ax_gauge)
    except ValueError:
        ax_gauge.clear()
        ax_gauge.set_facecolor("#161616")
        ax_gauge.text(
            0.5,
            0.5,
            "Aguardando dados da sessão...",
            ha="center",
            va="center",
            color="#dddddd",
            fontsize=12,
        )
        ax_gauge.axis("off")
    except Exception as exc:  # pylint: disable=broad-except
        ax_gauge.clear()
        ax_gauge.set_facecolor("#161616")
        ax_gauge.text(
            0.5,
            0.5,
            f"Erro gauge:\n{exc}",
            ha="center",
            va="center",
            color="#ffb347",
            fontsize=12,
        )
        ax_gauge.axis("off")

    try:
        render_sentiment_trend(scores_path, ax=ax_trend, max_points=60, since=SESSION_START)
    except ValueError:
        ax_trend.clear()
        ax_trend.set_facecolor("#161616")
        ax_trend.text(
            0.5,
            0.5,
            "Aguardando dados da sessão...",
            ha="center",
            va="center",
            color="#dddddd",
            fontsize=12,
        )
        ax_trend.axis("off")
    except Exception as exc:  # pylint: disable=broad-except
        ax_trend.clear()
        ax_trend.set_facecolor("#161616")
        ax_trend.text(
            0.5,
            0.5,
            f"Erro tendência:\n{exc}",
            ha="center",
            va="center",
            color="#ffb347",
            fontsize=12,
        )
        ax_trend.axis("off")

    variations_path = config.VARIATIONS_PATH
    ewz_display, ewz_color = "EWZ: N/D", NEUTRAL_COLOR
    dxy_display, dxy_color = "DXY: N/D", NEUTRAL_COLOR

    if variations_path.exists():
        try:
            _, ewz_text_value, ewz_decimal = load_latest_variation(
                "iShares MSCI Brazil ETF", variations_path, since=SESSION_START
            )
            ewz_display, ewz_color = _format_ticker_text("EWZ", ewz_text_value, ewz_decimal)
        except ValueError:
            ewz_display, ewz_color = "EWZ: N/D", NEUTRAL_COLOR
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[dashboard] Falha ao ler EWZ: {exc}")

        try:
            _, dxy_text_value, dxy_decimal = load_latest_variation(
                "Índice Dólar Futuros", variations_path, since=SESSION_START
            )
            dxy_display, dxy_color = _format_ticker_text("DXY", dxy_text_value, dxy_decimal)
        except ValueError:
            dxy_display, dxy_color = "DXY: N/D", NEUTRAL_COLOR
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[dashboard] Falha ao ler DXY: {exc}")

    _render_ticker_box(ax_ewz, ewz_display, ewz_color)
    _render_ticker_box(ax_dxy, dxy_display, dxy_color)


def launch_dashboard() -> None:
    plt.rcParams["toolbar"] = "None"
    fig = plt.figure(figsize=(12, 5.0))
    fig.canvas.manager.set_window_title("SMC TREND")
    fig.patch.set_facecolor("#111111")

    gridspec = fig.add_gridspec(3, 2, height_ratios=[3.2, 0.6, 1], hspace=0.15, wspace=0.3)
    ax_gauge = fig.add_subplot(gridspec[0, 0])
    ax_trend = fig.add_subplot(gridspec[0, 1])

    _wrap_with_card(ax_gauge)
    _wrap_with_card(ax_trend)

    ax_label_left = fig.add_subplot(gridspec[1, 0])
    ax_label_right = fig.add_subplot(gridspec[1, 1])
    for ax_label, text in ((ax_label_left, "TERMÔMETRO"), (ax_label_right, "SMC FLOW")):
        ax_label.axis("off")
        ax_label.text(
            0.5,
            0.65,
            text,
            ha="center",
            va="center",
            color="#f5f5f5",
            fontsize=13,
            fontweight="bold",
            family="DejaVu Sans",
        )
        ax_label.axhline(
            y=0.2,
            xmin=0.05,
            xmax=0.95,
            color="#444444",
            linewidth=4,
        )

    ax_ewz = fig.add_subplot(gridspec[2, 0])
    ax_dxy = fig.add_subplot(gridspec[2, 1])

    _update_axes(0, ax_gauge, ax_trend, ax_ewz, ax_dxy)
    anim = FuncAnimation(
        fig,
        _update_axes,
        fargs=(ax_gauge, ax_trend, ax_ewz, ax_dxy),
        interval=REFRESH_INTERVAL_SECONDS * 1000,
        cache_frame_data=False,
    )

    # Mantém referência à animação para evitar coleta de lixo prematura.
    fig._sentiment_anim = anim  # type: ignore[attr-defined]

    fig.suptitle("SMC TREND", color="#f5f5f5", fontsize=16, y=0.97)
    fig.subplots_adjust(left=0.06, right=0.94, top=0.92, bottom=0.08, hspace=0.22, wspace=0.28)
    plt.show()


if __name__ == "__main__":
    launch_dashboard()

