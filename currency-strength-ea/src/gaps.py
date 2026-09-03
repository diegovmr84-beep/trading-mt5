"""Detecção de gaps de dado, compartilhada entre os downloaders (MT5 e
Dukascopy) — mesma regra em ambos para não ter dois critérios divergentes
de "isso é um gap suspeito"."""

from __future__ import annotations

from datetime import timedelta

from src import db

# Tolerância de ~3 dias cobre o fechamento normal de fim de semana
# (sexta ~21-22h UTC até domingo ~21-22h UTC). Qualquer intervalo maior que
# isso entre candles M5 consecutivos é registrado para revisão manual.
GAP_THRESHOLD_SECONDS = timedelta(days=3).total_seconds()


def detect_and_log_gaps(conn, symbol_id: int, rows_sorted_by_ts: list[tuple]) -> int:
    """rows_sorted_by_ts: linhas de candles M5 já ordenadas por ts_utc
    (primeiro elemento da tupla). Retorna o número de gaps registrados."""
    gaps_found = 0
    for prev, cur in zip(rows_sorted_by_ts, rows_sorted_by_ts[1:]):
        delta = cur[0] - prev[0]
        if delta <= GAP_THRESHOLD_SECONDS:
            continue
        db.insert_data_gap(
            conn,
            symbol_id,
            prev[0],
            cur[0],
            note=f"gap de {delta / 3600:.1f}h entre candles consecutivos",
        )
        gaps_found += 1
    return gaps_found
