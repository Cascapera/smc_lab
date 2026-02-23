"""
Recomendações de capítulos/páginas dos livros com base nas 3 piores combinações.
Usa apenas: Setup, Entrada (entry_type), Gatilho (trigger), Parcial (partial_trade).
Livro 1 = Smart Money Concept (páginas). Livro 2 = The Black Book of Smart Money (capítulos).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Livro 1 (Smart Money Concept) – apenas páginas para Setup/Entrada/Parcial.
# Setup: só referenciar se nas piores houver pelo menos um de: flip, choch, continuation, liquidity.
# Gatilho: Livro 1 não tem referência → não usar.
# ---------------------------------------------------------------------------
SETUP_LIVRO_1 = {
    "flip": 83,
    "choch": 84,
    "continuation": 86,
    "liquidity": 87,
}
# Valores de setup que o Livro 1 cobre; outros (PD, FVG, falhas, duplos, N/D, Cunha) são ignorados.
LIVRO_1_SETUP_VALID = frozenset(SETUP_LIVRO_1.keys())

ENTRADA_LIVRO_1 = {
    "anticipated": 48,
    "confirmed": 63,
    "lateral": 48,
}

PARCIAL_LIVRO_1 = {
    "yes_neg": 102,  # Sim -5x1
}

# ---------------------------------------------------------------------------
# Livro 2 (The Black Book) – capítulos (string para manter 9.1, 10.2, etc.).
# Gatilho: só martelo_bf, rocadinha, fffd, region, passagem.
# Parcial: só yes_neg → 13.2.
# ---------------------------------------------------------------------------
SETUP_LIVRO_2 = {
    "flip": "9.1",
    "choch": "9.2",
    "continuation": "9.3",
    "liquidity": "9.4",
    "pd": "9.5",
    "fvg": "9.6",
    "top_failure": "9.7",
    "bottom_failure": "9.7",
    "double_top": "9.7",
    "double_bottom": "9.7",
    "none": "9",
    "wedge": "10.2",
}

ENTRADA_LIVRO_2 = {
    "anticipated": "12.1",
    "confirmed": "12.2",
    "lateral": "2.0",
}

GATILHO_LIVRO_2 = {
    "martelo_bf": "11.1",
    "rocadinha": "11.2",
    "fffd": "11.2",
    "region": "11.4",
    "passagem": "11.5",
}

PARCIAL_LIVRO_2 = {
    "yes_neg": "13.2",  # Sim -5x1
}

DIMENSIONS_USED = ("setup", "entry_type", "trigger", "partial_trade")


def get_book_recommendations_text(
    top3_worst_combos: list[dict],
    url_smart_money_concept: str = "",
    url_black_book: str = "",
) -> str:
    """
    A partir das top 3 piores combinações, monta o texto de recomendação (uma linha por livro)
    e links. Usa apenas Setup, Entrada, Gatilho e Parcial.
    """
    if not top3_worst_combos:
        return _links_only_block(url_smart_money_concept, url_black_book)

    # Coletar valores únicos por dimensão nas piores combinações
    setups = set()
    entradas = set()
    gatilhos = set()
    parciais = set()
    for row in top3_worst_combos:
        v = row.get("setup")
        if v:
            setups.add(v)
        v = row.get("entry_type")
        if v:
            entradas.add(v)
        v = row.get("trigger")
        if v:
            gatilhos.add(v)
        v = row.get("partial_trade")
        if v:
            parciais.add(v)

    # Livro 1: Setup só se houver pelo menos um de flip, choch, continuation, liquidity
    paginas_setup_1 = set()
    if setups & LIVRO_1_SETUP_VALID:
        for s in setups:
            if s in SETUP_LIVRO_1:
                paginas_setup_1.add(SETUP_LIVRO_1[s])

    paginas_entrada_1 = set()
    for e in entradas:
        if e in ENTRADA_LIVRO_1:
            paginas_entrada_1.add(ENTRADA_LIVRO_1[e])

    paginas_parcial_1 = set()
    for p in parciais:
        if p in PARCIAL_LIVRO_1:
            paginas_parcial_1.add(PARCIAL_LIVRO_1[p])

    # Livro 2
    capitulos_setup_2 = set()
    for s in setups:
        if s in SETUP_LIVRO_2:
            capitulos_setup_2.add(SETUP_LIVRO_2[s])

    capitulos_entrada_2 = set()
    for e in entradas:
        if e in ENTRADA_LIVRO_2:
            capitulos_entrada_2.add(ENTRADA_LIVRO_2[e])

    capitulos_gatilho_2 = set()
    for g in gatilhos:
        if g in GATILHO_LIVRO_2:
            capitulos_gatilho_2.add(GATILHO_LIVRO_2[g])

    capitulos_parcial_2 = set()
    for p in parciais:
        if p in PARCIAL_LIVRO_2:
            capitulos_parcial_2.add(PARCIAL_LIVRO_2[p])

    # Montar uma linha por livro
    parts_smc = []
    if paginas_setup_1:
        parts_smc.append("Setup – p. " + ", ".join(str(x) for x in sorted(paginas_setup_1)))
    if paginas_entrada_1:
        parts_smc.append("Entrada – p. " + ", ".join(str(x) for x in sorted(paginas_entrada_1)))
    if paginas_parcial_1:
        parts_smc.append("Parcial – p. " + ", ".join(str(x) for x in sorted(paginas_parcial_1)))

    parts_black = []
    if capitulos_setup_2:
        parts_black.append("Setup – " + ", ".join(_sort_chapter(capitulos_setup_2)))
    if capitulos_entrada_2:
        parts_black.append("Entrada – " + ", ".join(_sort_chapter(capitulos_entrada_2)))
    if capitulos_gatilho_2:
        parts_black.append("Gatilho – " + ", ".join(_sort_chapter(capitulos_gatilho_2)))
    if capitulos_parcial_2:
        parts_black.append("Parcial – " + ", ".join(_sort_chapter(capitulos_parcial_2)))

    lines = [
        "Para melhorar suas operações recomendo que você estude os seguintes pontos:",
        "",
    ]

    if parts_smc:
        lines.append("No Livro Smart Money Concept estude: " + "; ".join(parts_smc) + ".")
    else:
        lines.append(
            "No Livro Smart Money Concept estude os pontos indicados na sua análise (confira o conteúdo do livro)."
        )

    if parts_black:
        lines.append(
            "No Livro The Black Book of Smart Money estude: " + "; ".join(parts_black) + "."
        )
    else:
        lines.append(
            "No Livro The Black Book of Smart Money estude os pontos indicados na sua análise (confira o conteúdo do livro)."
        )

    lines.extend(["", "Caso ainda não tenha os livros você poderá comprar nos links abaixo:", ""])

    if url_smart_money_concept:
        lines.append(f"Smart Money Concept: {url_smart_money_concept}")
    else:
        lines.append("Smart Money Concept: (configure BOOK_SMART_MONEY_CONCEPT_URL no .env)")

    if url_black_book:
        lines.append(f"The Black Book of Smart Money: {url_black_book}")
    else:
        lines.append("The Black Book of Smart Money: (configure BOOK_BLACK_BOOK_URL no .env)")

    return "\n".join(lines)


def _sort_chapter(cap_set: set) -> list[str]:
    """Ordena capítulos como 9, 9.1, 9.2, 9.7, 10.2, 11.1, etc."""

    def key(s):
        try:
            parts = s.split(".", 1)
            a = int(parts[0])
            b = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            return (a, b)
        except (ValueError, AttributeError):
            return (0, 0)

    return sorted(cap_set, key=key)


def _links_only_block(url_smart_money_concept: str, url_black_book: str) -> str:
    """Quando não há piores combinações, só mostra os links."""
    lines = [
        "Para melhorar suas operações recomendo que você estude os pontos indicados na sua análise.",
        "",
        "Caso ainda não tenha os livros você poderá comprar nos links abaixo:",
        "",
    ]
    if url_smart_money_concept:
        lines.append(f"Smart Money Concept: {url_smart_money_concept}")
    else:
        lines.append("Smart Money Concept: (configure BOOK_SMART_MONEY_CONCEPT_URL no .env)")
    if url_black_book:
        lines.append(f"The Black Book of Smart Money: {url_black_book}")
    else:
        lines.append("The Black Book of Smart Money: (configure BOOK_BLACK_BOOK_URL no .env)")
    return "\n".join(lines)
