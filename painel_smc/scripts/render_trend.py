# Script CLI para gerar o gráfico de tendência do sentimento
from pathlib import Path

import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import config  # noqa: E402
from core.visuals import load_trend_series, render_sentiment_trend  # noqa: E402


def main() -> None:
    scores_path = config.SCORES_PATH
    if not scores_path.exists():
        raise FileNotFoundError(f"Arquivo '{scores_path}' não encontrado. Gere dados antes.")

    series = load_trend_series(scores_path)
    latest_label = str(series.index[-1]) if not series.empty else "sem_dados"

    output_path = config.DATA_DIR / "visualizacoes" / f"tendencia_{latest_label.replace(':', '-')}.png"
    render_sentiment_trend(scores_path, output_path=output_path)
    print(f"Tendência gerada em: {output_path}")


if __name__ == "__main__":
    main()

