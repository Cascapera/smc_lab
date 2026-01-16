# Script de linha de comando para gerar o gauge de sentimento
from pathlib import Path

# Ajuste para permitir imports do pacote core
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import config  # noqa: E402
from core.visuals import load_latest_score, render_market_sentiment_gauge  # noqa: E402


def main() -> None:
    score, label = load_latest_score(config.SCORES_PATH)
    output_path = config.DATA_DIR / "visualizacoes" / f"sentimento_{label.replace(':', '-')}.png"
    render_market_sentiment_gauge(score, output_path=output_path)
    print(f"Gauge gerado em: {output_path}")


if __name__ == "__main__":
    main()