#!/usr/bin/env python3
"""Fase 2: calcula o índice de força (Métodos A e C, src/force_index.py)
para os 8 majors, nas três variantes de janela de retorno (src/windows.py),
usando o histórico M5 dos 28 pares cruzados (Fase 1) — e grava tudo na
tabela `force_index`.

Uso:
    python -m scripts.compute_force_index                   # as 3 variantes
    python -m scripts.compute_force_index --variant daily    # só uma
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from src import db
from src.force_index import compute_force_index, force_index_to_rows
from src.pairs import generate_pairs
from src.windows import WINDOW_VARIANTS


def load_closes(conn) -> dict[str, pd.Series]:
    """Carrega o close M5 de cada um dos 28 pares canônicos (Fase 1),
    indexado por timestamp UTC — pronto pra compute_force_index."""
    closes: dict[str, pd.Series] = {}
    for pair in generate_pairs():
        df = pd.read_sql_query(
            "SELECT c.ts_utc, c.close FROM candles_m5 c JOIN symbols s ON s.id = c.symbol_id "
            "WHERE s.name = ? ORDER BY c.ts_utc",
            conn,
            params=(pair,),
        )
        if df.empty:
            print(f"  AVISO: {pair} sem candles — pulando (índice ficará sem esse par)", file=sys.stderr)
            continue
        idx = pd.to_datetime(df["ts_utc"], unit="s", utc=True)
        closes[pair] = pd.Series(df["close"].to_numpy(), index=idx)
    return closes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=WINDOW_VARIANTS, default=None, help="default: calcula as 3 variantes"
    )
    args = parser.parse_args()
    variants = [args.variant] if args.variant else list(WINDOW_VARIANTS)

    conn = db.connect(config.DB_PATH)

    print("Carregando candles M5 dos 28 pares...")
    t0 = time.monotonic()
    closes = load_closes(conn)
    print(f"  {len(closes)}/28 pares carregados em {time.monotonic() - t0:.1f}s")
    if len(closes) < 28:
        print("  AVISO: índice será calculado com menos de 28 pares — ver avisos acima.", file=sys.stderr)

    for variant in variants:
        print(f"\n=== variante: {variant} ===")
        t0 = time.monotonic()
        force_a, rank_c = compute_force_index(closes, variant)
        print(f"  calculado em {time.monotonic() - t0:.1f}s | {len(force_a):,} timestamps")

        rows = force_index_to_rows(force_a, rank_c, variant)
        db.delete_force_index_for_variant(conn, variant)
        t0 = time.monotonic()
        db.insert_force_index(conn, rows)
        print(f"  gravado: {len(rows):,} linhas em {time.monotonic() - t0:.1f}s")

    conn.close()
    print("\nConcluído.")


if __name__ == "__main__":
    main()
