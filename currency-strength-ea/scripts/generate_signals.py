#!/usr/bin/env python3
"""Fase 3: gera a lista histórica de sinais candidatos (sem P&L).

Para cada variante de janela (Fase 2) e cada limiar `k_min`:
  1. z-score par-a-par e eventos de ONSET de sinal (src/signals.py);
  2. calibra stop/take SÓ com eventos de desenvolvimento (src/calibration.py,
     que recusa dado de validação) e aplica a tabela a todos os eventos;
  3. aplica o filtro de spread por par/sessão (src/spread_model.py);
  4. grava em `signal_candidates` / `stop_take_calibration`.

Não calcula nenhuma estatística de resultado (MFE/MAE/retorno) de eventos do
período de validação — o out-of-sample só é aberto na Fase 4.

Uso:
    python -m scripts.generate_signals                          # 3 variantes x k=5,6,7
    python -m scripts.generate_signals --variant overlap --k 5
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
from src.calibration import (
    CalibrationParams,
    add_excursions,
    apply_calibration,
    calibrate_stop_take,
    embargo_seconds,
)
from src.force_index import compute_force_index
from src.loaders import load_ohlc
from src.signals import SignalParams, candidate_events, pair_zscores
from src.split import DEV_FRACTION, dev_cutoff
from src.spread_model import SpreadParams, apply_spread_filter, spread_table
from src.windows import WINDOW_VARIANTS


def _epoch(ts) -> list[int]:
    return pd.DatetimeIndex(ts).as_unit("s").astype("int64").tolist()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=WINDOW_VARIANTS, default=None, help="default: as 3")
    p.add_argument("--k", type=int, nargs="+", default=[5, 6, 7])
    p.add_argument("--z-crit", type=float, default=2.0)
    p.add_argument("--horizon", type=int, default=36)
    p.add_argument("--q-take", type=float, default=0.5)
    p.add_argument("--q-stop", type=float, default=0.75)
    p.add_argument("--n-buckets", type=int, default=4)
    p.add_argument("--spread-quantile", type=float, default=0.75)
    p.add_argument("--max-spread-to-take", type=float, default=0.25)
    args = p.parse_args()
    variants = [args.variant] if args.variant else list(WINDOW_VARIANTS)

    cal = CalibrationParams(horizon=args.horizon, q_take=args.q_take, q_stop=args.q_stop, n_buckets=args.n_buckets)
    spr = SpreadParams(quantile=args.spread_quantile, max_spread_to_take=args.max_spread_to_take)

    conn = db.connect(config.DB_PATH)
    print("Carregando OHLC M5 dos 28 pares...")
    t0 = time.monotonic()
    ohlc = load_ohlc(conn)
    closes = {pair: df["close"] for pair, df in ohlc.items()}
    print(f"  {len(ohlc)}/28 pares em {time.monotonic() - t0:.0f}s")

    ts_min = min(int(df.index.as_unit("s").astype("int64")[0]) for df in ohlc.values())
    ts_max = max(int(df.index.as_unit("s").astype("int64")[-1]) for df in ohlc.values())
    cutoff = dev_cutoff(ts_min, ts_max)
    cutoff_dt = pd.Timestamp(cutoff, unit="s", tz="UTC")
    print(f"Corte dev/validação ({DEV_FRACTION:.0%}): {cutoff_dt:%Y-%m-%d %H:%M} UTC")

    sp_table = spread_table(conn, spr.quantile)
    print(f"Tabela de spread: {len(sp_table)} combinações (par, sessão), quantil {spr.quantile}")

    for variant in variants:
        print(f"\n=== variante: {variant} ===")
        t0 = time.monotonic()
        z_wide, sigma_wide = pair_zscores(closes, variant)
        force_a, rank_c = compute_force_index(closes, variant)
        print(f"  z-scores + força em {time.monotonic() - t0:.0f}s")

        for k in args.k:
            sig = SignalParams(k_min=k, z_crit=args.z_crit)
            param_set = (
                f"k{k}_z{args.z_crit}_H{cal.horizon}_qt{cal.q_take}_qs{cal.q_stop}"
                f"_sq{spr.quantile}_sf{spr.max_spread_to_take}"
            )
            events = candidate_events(z_wide, sigma_wide, force_a, rank_c, sig)
            if events.empty:
                print(f"  k={k}: nenhum evento")
                continue
            ev_epoch = pd.DatetimeIndex(events["ts"]).as_unit("s").astype("int64").to_numpy()
            embargo = embargo_seconds(cal)
            is_dev = ev_epoch + embargo <= cutoff      # resultado inteiro dentro do desenvolvimento
            is_val = ev_epoch >= cutoff
            events["period"] = ["dev" if d else ("val" if v else "embargo") for d, v in zip(is_dev, is_val)]

            # Excursões só dos eventos de DESENVOLVIMENTO (variável-resposta da calibração).
            dev_events = events[is_dev].reset_index(drop=True)
            dev_events = add_excursions(dev_events, lambda pair: ohlc[pair], cal)
            table = calibrate_stop_take(dev_events, cutoff, cal)

            events = apply_calibration(events, table, cal.horizon)
            events = apply_spread_filter(events, sp_table, spr)

            db.replace_stop_take_calibration(
                conn, param_set, variant,
                [(int(r.bucket), float(r.z_lo), float(r.z_hi), float(r.take_z), float(r.stop_z),
                  int(r.n_events), cutoff) for r in table.itertuples()],
            )
            cols = ["ts", "pair", "direction", "strong_ccy", "weak_ccy", "n_strong", "n_weak", "z_pair",
                    "force_gap", "rank_c_strong", "rank_c_weak", "priority", "sigma1", "bucket",
                    "take_rel", "stop_rel", "session", "spread_rel", "spread_ok", "period"]
            data = {c: events[c].tolist() for c in cols}
            data["ts"] = _epoch(events["ts"])
            data["spread_ok"] = [int(bool(x)) for x in data["spread_ok"]]
            rows = [(param_set, variant, *vals) for vals in zip(*(data[c] for c in cols))]
            db.replace_signal_candidates(conn, param_set, variant, rows)

            n_dev, n_val = int(is_dev.sum()), int(is_val.sum())
            n_emb = len(events) - n_dev - n_val
            ok = events["spread_ok"]
            tradable = events[ok]
            simult = tradable.groupby("ts").size()
            print(
                f"  k={k}: {len(events):,} eventos (dev {n_dev:,} / val {n_val:,} / embargo {n_emb}) | "
                f"passam no spread: {100 * ok.mean():.0f}% | trades simultâneos por instante "
                f"(só os que passam): média {simult.mean():.2f}, máx {simult.max() if len(simult) else 0}"
            )

    conn.close()
    print("\nConcluído.")


if __name__ == "__main__":
    main()
