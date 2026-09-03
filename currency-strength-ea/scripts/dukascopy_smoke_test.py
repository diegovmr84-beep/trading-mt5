#!/usr/bin/env python3
"""Teste de sanidade: baixa UMA hora real de UM par da Dukascopy e mostra o
resultado decodificado. Rode isto e confira visualmente os números antes de
disparar download_history_dukascopy.py para vários anos — a lógica de
decodificação (src/dukascopy.py) não foi validada contra um arquivo real
neste projeto (o ambiente onde foi escrita não tem acesso à Dukascopy).

O que checar no output:
- Preços na faixa plausível para o par (ex: EURUSD por volta de 1.0-1.2,
  USDJPY por volta de 140-160 em 2024/2025 — não 0.0001 nem 100000)
- Timestamps do primeiro/último tick dentro da hora pedida
- Número de candles M5 gerados (esperado: até 12 por hora, menos se a hora
  tiver poucos ticks)

Uso:
    python -m scripts.dukascopy_smoke_test --pair EURUSD --date 2024-06-04 --hour 10
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dukascopy import bi5_url, decode_bi5, hour_start_epoch, ticks_to_m5_candles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", default="EURUSD")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (UTC)")
    parser.add_argument("--hour", type=int, required=True, help="0-23 UTC")
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    dt_hour = day.replace(hour=args.hour)

    url = bi5_url(args.pair, dt_hour)
    print(f"Baixando: {url}")

    resp = requests.get(url, timeout=30)
    print(f"HTTP {resp.status_code}, {len(resp.content)} bytes")

    if resp.status_code == 404:
        print("404 — hora sem arquivo (par pode não existir, ou data fora do histórico coberto).")
        return
    resp.raise_for_status()

    ticks = decode_bi5(resp.content, args.pair)
    print(f"\n{len(ticks)} ticks decodificados.")

    if not ticks:
        print("Hora sem ticks (comum em fins de semana/feriado). Tente outro horário/dia.")
        return

    print(f"Primeiro tick: ms_offset={ticks[0].ms_offset}  ask={ticks[0].ask}  bid={ticks[0].bid}")
    print(f"Último tick:   ms_offset={ticks[-1].ms_offset}  ask={ticks[-1].ask}  bid={ticks[-1].bid}")

    rows = ticks_to_m5_candles(args.pair, hour_start_epoch(dt_hour), ticks)
    print(f"\n{len(rows)} candles M5 gerados:")
    print("ts_utc | open | high | low | close | n_ticks | spread_pts")
    for ts, o, h, l, c, n, _rv, spread in rows:
        ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")
        print(f"{ts_str} | {o:.5f} | {h:.5f} | {l:.5f} | {c:.5f} | {n:5d} | {spread}")


if __name__ == "__main__":
    main()
