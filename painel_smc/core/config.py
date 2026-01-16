# Configurações centrais do projeto: caminhos, parâmetros de scraping e agenda
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependência opcional
    load_dotenv = None

# Carrega variáveis de ambiente de um .env local, se disponível
if load_dotenv:
    load_dotenv()


# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Caminhos dos arquivos de dados
DATA_SOURCE_PATH = DATA_DIR / "planilha_referencia.xlsx"
VARIATIONS_PATH = DATA_DIR / "historico_variacoes.csv"
METADATA_PATH = DATA_DIR / "historico_variacoes_metadata.csv"
SCORES_PATH = DATA_DIR / "historico_scores.csv"
DEBUG_PATH = DATA_DIR / "debug_fontes_investing.txt"

# Parâmetros de scraping
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]
FETCH_DELAY_RANGE = (0.5, 1.0)
MAX_FETCH_ATTEMPTS = 3
FALLBACK_HOST = "https://r.jina.ai"

# Parâmetros de agenda
TARGET_INTERVAL_MINUTES = 5
LEAD_TIME_MINUTES = 2

