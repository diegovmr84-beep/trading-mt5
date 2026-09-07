#!/usr/bin/env python3
"""Fase 1, item 3: amostragem contínua de spread AO VIVO para os 28 pares.

Roda em loop, coletando bid/ask reais em intervalos regulares, taggeados
por sessão (Tóquio/Londres/NY/overlap/other). Isso é levantamento de dado
de mercado real (Seção 6 do estudo) — não deve ser estimado nem
substituído por número "de memória".

Rodar por tempo suficiente para cobrir todas as sessões várias vezes (o
estudo não fixa um mínimo; recomenda-se pelo menos 2-3 semanas corridas
para ter amostras de baixa e alta liquidez em cada sessão, incluindo
segunda de manhã pós-gap de fim de semana). Pode ser interrompido e
retomado a qualquer momento (Ctrl+C) sem perder o que já foi coletado —
cada amostra é gravada e commitada individualmente.

Uso:
    python -m scripts.spread_sampler                 # roda indefinidamente
    python -m scripts.spread_sampler --hours 168      # roda por 1 semana e para
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db
from src.mt5_connector import MT5ConnectionError, connect
from src.pairs import split_pair
from src.sessions import classify_session

# Coletor de longa duração (semanas): uma falha transitória de "database is
# locked" (ex: backfill de histórico escrevendo no mesmo arquivo, ou um
# VACUUM) não pode derrubar o processo. Tenta de novo com backoff; se ainda
# assim falhar, perde só o ciclo atual e segue.
DB_WRITE_RETRIES = 5
DB_WRITE_BACKOFF_SECONDS = 2.0


def _write_samples(conn: sqlite3.Connection, batch: list[tuple]) -> bool:
    for attempt in range(DB_WRITE_RETRIES):
        try:
            db.insert_spread_samples(conn, batch)
            return True
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == DB_WRITE_RETRIES - 1:
                print(
                    f"  AVISO: {len(batch)} amostras descartadas (falha ao gravar): {exc}",
                    file=sys.stderr,
                )
                return False
            time.sleep(DB_WRITE_BACKOFF_SECONDS * (attempt + 1))
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=None, help="duração máxima em horas (default: indefinido)")
    args = parser.parse_args()

    deadline = None
    if args.hours is not None:
        deadline = time.monotonic() + args.hours * 3600

    conn = db.connect(config.DB_PATH)
    symbol_ids: dict[str, int] = {}
    for canonical in config.PAIRS:
        base, quote = split_pair(canonical)
        symbol_ids[canonical] = db.upsert_symbol(conn, canonical, base, quote)

    print(f"Amostrando spread a cada {config.SPREAD_SAMPLE_INTERVAL_SECONDS}s. Ctrl+C para parar.")

    try:
        with connect() as mt5:
            for mt5_symbol in config.MT5_SYMBOLS:
                mt5.symbol_select(mt5_symbol, True)

            n_samples = 0
            while deadline is None or time.monotonic() < deadline:
                now = datetime.now(timezone.utc)
                session = classify_session(now)
                ts_utc = int(now.timestamp())

                batch: list[tuple] = []
                for canonical, mt5_symbol in zip(config.PAIRS, config.MT5_SYMBOLS):
                    tick = mt5.symbol_info_tick(mt5_symbol)
                    if tick is None or tick.bid == 0 or tick.ask == 0:
                        continue  # símbolo sem cotação no momento (mercado fechado etc.)
                    batch.append(
                        (
                            symbol_ids[canonical],
                            ts_utc,
                            session,
                            float(tick.bid),
                            float(tick.ask),
                            float(tick.ask - tick.bid),
                        )
                    )

                if batch and _write_samples(conn, batch):
                    n_samples += len(batch)

                if n_samples % 500 < len(config.PAIRS):
                    print(f"  [{now.isoformat()}] sessão={session} amostras acumuladas={n_samples}")

                time.sleep(config.SPREAD_SAMPLE_INTERVAL_SECONDS)

    except MT5ConnectionError as exc:
        print(f"\nERRO: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário. Amostras já coletadas estão salvas no banco.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
