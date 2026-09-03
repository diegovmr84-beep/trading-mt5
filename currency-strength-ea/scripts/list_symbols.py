#!/usr/bin/env python3
"""Utilitário de diagnóstico: descobre como a corretora nomeia os símbolos
dos majors na conta logada, para calibrar MT5_SYMBOL_SUFFIX no config.

Nunca assume o nome do símbolo — pergunta direto ao MT5 via mt5.symbols_get(),
que é a forma correta de descobrir isso (a interface do terminal pode
esconder/reordenar grupos e induzir a erro de leitura).

Uso:
    python -m scripts.list_symbols
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mt5_connector import MT5ConnectionError, connect
from src.pairs import generate_pairs


def main() -> None:
    canonical_pairs = generate_pairs()

    try:
        with connect() as mt5:
            all_symbols = mt5.symbols_get()
    except MT5ConnectionError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        sys.exit(1)

    all_names = {s.name for s in all_symbols}

    print(f"Total de símbolos visíveis nesta conta: {len(all_names)}\n")

    exact_matches = [p for p in canonical_pairs if p in all_names]
    print(f"Pares canônicos encontrados SEM sufixo: {len(exact_matches)}/28")

    if len(exact_matches) == 28:
        print("-> Conta não usa sufixo. Deixe MT5_SYMBOL_SUFFIX vazio (ou não defina a variável).")
        return

    print("\nProcurando variantes com sufixo para os pares não encontrados...")
    missing = [p for p in canonical_pairs if p not in all_names]
    suffix_candidates: dict[str, int] = {}

    for pair in missing:
        matches = [name for name in all_names if name.startswith(pair) and name != pair]
        for m in matches:
            suffix = m[len(pair):]
            suffix_candidates[suffix] = suffix_candidates.get(suffix, 0) + 1
        if matches:
            print(f"  {pair} -> encontrado(s) como: {matches}")
        else:
            print(f"  {pair} -> NENHUMA variante encontrada (nome pode ser totalmente diferente, checar manualmente)")

    if suffix_candidates:
        best_suffix = max(suffix_candidates, key=suffix_candidates.get)
        print(f"\nSufixo mais consistente entre os pares: '{best_suffix}' ({suffix_candidates[best_suffix]}/28 pares)")
        print(f"-> Defina MT5_SYMBOL_SUFFIX={best_suffix}")
    else:
        print("\nNenhum padrão de sufixo identificado automaticamente. Liste os símbolos manualmente:")
        for name in sorted(all_names):
            print(f"  {name}")


if __name__ == "__main__":
    main()
