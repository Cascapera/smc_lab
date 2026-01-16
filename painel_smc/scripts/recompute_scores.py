# Ferramenta de apoio para recalcular o historico_scores com a nova lógica
from pathlib import Path
from typing import List

import pandas as pd

# Ajusta o sys.path para permitir importações do pacote core quando executado via CLI
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import assets, config, writers  # noqa: E402
from core.models import VariationResult  # noqa: E402
from core.utils import parse_variation_percent  # noqa: E402


# Constrói a lista de resultados a partir de uma coluna de histórico existente
def _build_results(df: pd.DataFrame, column: str) -> List[VariationResult]:
    asset_by_name = {asset.name: asset for asset in assets.load_assets()}
    results: List[VariationResult] = []
    for _, row in df.iterrows():
        asset_name = row["Ativo"]
        asset = asset_by_name.get(asset_name)
        if asset is None:
            raise ValueError(f"Ativo '{asset_name}' não encontrado na planilha de referência.")

        raw_value = row[column]
        if pd.isna(raw_value):
            variation_text = None
        else:
            variation_text = str(raw_value).strip() or None
        variation_decimal = parse_variation_percent(variation_text)

        results.append(
            VariationResult(
                asset=asset,
                variation_text=variation_text,
                variation_decimal=variation_decimal,
                status="historical",
            )
        )
    return results


# Executa o recálculo para cada coluna (janela) registrada anteriormente
def regenerate_scores() -> None:
    path = config.VARIATIONS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de variações '{path}' não encontrado.")

    df = pd.read_csv(path)
    if "Ativo" not in df.columns:
        raise ValueError("Coluna 'Ativo' ausente no histórico de variações.")

    score_columns = [col for col in df.columns if col != "Ativo"]
    for column in score_columns:
        results = _build_results(df, column)
        writers.write_scores(results, column)

    print("Arquivo historico_scores.csv regenerado com a nova lógica.")


# Permite execução via linha de comando
if __name__ == "__main__":
    regenerate_scores()

