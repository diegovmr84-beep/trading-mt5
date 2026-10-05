#!/usr/bin/env python3
"""Fase 4 — varredura no período de DESENVOLVIMENTO (itens 2, 3, 6, 8).

Roda as 9 configurações (3 janelas x k=5/6/7) nos 3 cenários de custo, escolhe a
configuração pela regra pré-registrada (src/backtest_config.py), e roda o
walk-forward. NUNCA lê o período de validação: `load_events` só aceita 'dev' ou
'val' explícito, e aqui só se pede 'dev'.

Escreve reports/fase4_dev_results.json (que deve ser commitado ANTES de abrir a
validação, para a escolha da configuração ficar registrada no histórico).

Uso:
    python -m scripts.run_backtest_dev
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from src import backtest_config as cfg
from src import db
from src.backtest import apply_scenario, simulate_trades
from src.backtest_io import clear_trades, config_id, configs, jsonable, load_events, save_trades
from src.calibration import CalibrationParams, add_excursions
from src.loaders import load_ohlc
from src.split import dev_cutoff
from src.validation_stats import cluster_mean_test, day_clusters, select_config, summarize
from src.walkforward import walk_forward


def main() -> None:
    conn = db.connect(config.DB_PATH)
    print("Carregando OHLC M5...")
    t0 = time.monotonic()
    ohlc = load_ohlc(conn)
    print(f"  {len(ohlc)} pares em {time.monotonic() - t0:.0f}s")
    ts_min = min(int(d.index.as_unit("s").astype("int64")[0]) for d in ohlc.values())
    ts_max = max(int(d.index.as_unit("s").astype("int64")[-1]) for d in ohlc.values())
    cutoff = dev_cutoff(ts_min, ts_max)
    cal = CalibrationParams(horizon=cfg.HORIZON)

    clear_trades(conn, "dev_sweep")
    clear_trades(conn, "walk_forward")

    sweep_rows, dev_events = [], {}
    for variant, k in configs():
        cid = config_id(variant, k)
        events = load_events(conn, variant, k, "dev")
        if events.empty:
            print(f"  {cid}: sem eventos de desenvolvimento")
            continue
        assert (pd.DatetimeIndex(events["ts"]).as_unit("s").astype("int64").to_numpy() < cutoff).all()
        gross = simulate_trades(events, ohlc, cfg.HORIZON)
        for name, scenario in cfg.SCENARIOS.items():
            net = apply_scenario(gross, scenario)
            row = {"config": cid, "variant": variant, "k": k, "scenario": name, "n_events": len(events)}
            row.update(summarize(net))
            sweep_rows.append(row)
            save_trades(conn, net, "dev_sweep", cid, name, "dev")
        dev_events[cid] = add_excursions(events, lambda p: ohlc[p], cal)
        r = next(x for x in sweep_rows[::-1] if x["config"] == cid and x["scenario"] == cfg.PRIMARY_SCENARIO)
        print(f"  {cid:12s} eventos {len(events):5d} | {cfg.PRIMARY_SCENARIO}: n={r.get('n', 0):5d} "
              f"líq={r.get('mean_bps', float('nan')):7.2f} bps  t={r.get('t', float('nan')):6.2f}  R={r.get('exp_R', float('nan')):6.3f}")

    primary = [r for r in sweep_rows if r["scenario"] == cfg.PRIMARY_SCENARIO]
    chosen = select_config(primary)
    print(f"\nConfiguração escolhida (regra pré-registrada): {chosen.get('config')}")

    print("\nWalk-forward (só desenvolvimento)...")
    t0 = time.monotonic()
    folds, wf_trades = walk_forward(dev_events, ohlc, cutoff, cfg.SCENARIOS[cfg.PRIMARY_SCENARIO], cal)
    print(f"  {len(folds)} dobras em {time.monotonic() - t0:.0f}s")
    wf = {"n_folds": int(len(folds)), "n_folds_with_trades": int((folds["test_n"] > 0).sum()) if len(folds) else 0}
    if len(wf_trades):
        mt = cluster_mean_test(wf_trades["net_ret"].to_numpy(), day_clusters(wf_trades["ts"]))
        by_month = wf_trades.groupby("fold_train_end")["net_ret"].mean()
        wf.update({
            "n_trades": mt.n, "mean_bps": mt.mean * 1e4, "t": mt.t, "p_two": mt.p_two,
            "months_positive": float((by_month > 0).mean()), "n_months": int(len(by_month)),
            "configs_chosen": folds["config"].value_counts().to_dict(),
        })
        save_trades(conn, wf_trades.assign(scenario=cfg.PRIMARY_SCENARIO), "walk_forward", "wf_selected", cfg.PRIMARY_SCENARIO, "dev")
    else:
        wf["mean_bps"] = None
    print(f"  WF: {wf}")

    out = {
        "cutoff_ts": cutoff,
        "cutoff_utc": pd.Timestamp(cutoff, unit="s", tz="UTC").isoformat(),
        "sweep": sweep_rows,
        "chosen": chosen,
        "walk_forward": wf,
        "folds": folds.to_dict("records"),
        "m_tests": cfg.M_TESTS,
        "alpha_bonferroni": cfg.ALPHA_BONFERRONI,
    }
    path = Path("reports/fase4_dev_results.json")
    path.write_text(json.dumps(jsonable(out), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nescrito: {path}")
    conn.close()


if __name__ == "__main__":
    main()
