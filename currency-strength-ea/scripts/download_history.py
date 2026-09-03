#!/usr/bin/env python3
"""Fase 1, item 1-2: baixa candles M5 dos 28 pares cruzados (jan/2020 até
hoje) do MT5/Exness e armazena em SQLite.

Só roda numa máquina Windows com o terminal MT5 da Exness instalado e
logado (ver README.md). Detecta e registra gaps de dados (Fase 1, item 4)
em vez de simplesmente ignorá-los.

Uso:
    python -m scripts.download_history
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db
from src.gaps import detect_and_log_gaps
from src.mt5_connector import MT5ConnectionError, connect
from src.pairs import split_pair


def _iter_chunks(start: datetime, end: datetime, chunk_days: int):
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        yield cur, nxt
        cur = nxt


def main() -> None:
    start = datetime.fromisoformat(config.HISTORY_START_UTC)
    end = datetime.now(timezone.utc)

    conn = db.connect(config.DB_PATH)

    try:
        with connect() as mt5:
            timeframe = mt5.TIMEFRAME_M5

            for canonical, mt5_symbol in zip(config.PAIRS, config.MT5_SYMBOLS):
                base, quote = split_pair(canonical)
                print(f"\n=== {canonical} (símbolo MT5: {mt5_symbol}) ===")

                if not mt5.symbol_select(mt5_symbol, True):
                    print(f"  AVISO: símbolo '{mt5_symbol}' não encontrado/selecionável nesta conta. Pulando.")
                    continue

                symbol_id = db.upsert_symbol(conn, canonical, base, quote)

                all_rows: list[tuple] = []
                for chunk_start, chunk_end in _iter_chunks(start, end, config.DOWNLOAD_CHUNK_DAYS):
                    rates = mt5.copy_rates_range(mt5_symbol, timeframe, chunk_start, chunk_end)
                    if rates is None or len(rates) == 0:
                        continue
                    rows = [
                        (
                            int(r["time"]),
                            float(r["open"]),
                            float(r["high"]),
                            float(r["low"]),
                            float(r["close"]),
                            int(r["tick_volume"]),
                            int(r["real_volume"]),
                            int(r["spread"]),
                        )
                        for r in rates
                    ]
                    db.insert_candles(conn, symbol_id, rows)
                    all_rows.extend(rows)
                    print(f"  {chunk_start.date()} -> {chunk_end.date()}: {len(rows)} candles")

                all_rows.sort(key=lambda r: r[0])
                db.delete_data_gaps_for_symbol(conn, symbol_id)
                gaps = detect_and_log_gaps(conn, symbol_id, all_rows)
                print(f"  total: {len(all_rows)} candles | gaps suspeitos registrados: {gaps}")

    except MT5ConnectionError as exc:
        print(f"\nERRO: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
