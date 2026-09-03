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

                for canonical, mt5_symbol in zip(config.PAIRS, config.MT5_SYMBOLS):
                    tick = mt5.symbol_info_tick(mt5_symbol)
                    if tick is None or tick.bid == 0 or tick.ask == 0:
                        continue  # símbolo sem cotação no momento (mercado fechado etc.)
                    spread_points = tick.ask - tick.bid
                    db.insert_spread_sample(
                        conn,
                        symbol_ids[canonical],
                        int(now.timestamp()),
                        session,
                        float(tick.bid),
                        float(tick.ask),
                        float(spread_points),
                    )
                    n_samples += 1

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
