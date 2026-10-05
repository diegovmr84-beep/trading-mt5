"""Carregamento do histórico M5 (Fase 1) para as fases de cálculo."""

from __future__ import annotations

import sys

import pandas as pd

from src.pairs import generate_pairs


def load_ohlc(conn) -> dict[str, pd.DataFrame]:
    """OHLC M5 de cada um dos 28 pares canônicos, indexado por timestamp UTC
    (DatetimeIndex, resolução em segundos). Par sem candle é pulado com aviso."""
    out: dict[str, pd.DataFrame] = {}
    for pair in generate_pairs():
        df = pd.read_sql_query(
            "SELECT c.ts_utc, c.open, c.high, c.low, c.close FROM candles_m5 c "
            "JOIN symbols s ON s.id = c.symbol_id WHERE s.name = ? ORDER BY c.ts_utc",
            conn,
            params=(pair,),
        )
        if df.empty:
            print(f"  AVISO: {pair} sem candles — pulando", file=sys.stderr)
            continue
        idx = pd.DatetimeIndex(pd.to_datetime(df.pop("ts_utc"), unit="s", utc=True))
        df.index = idx
        out[pair] = df
    return out
