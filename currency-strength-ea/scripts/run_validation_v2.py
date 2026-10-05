#!/usr/bin/env python3
"""Fase 4b — abre o OUT-OF-SAMPLE UMA ÚNICA VEZ para a hipótese H1 da v2.

Aplica, sem nenhum reajuste, a regra pré-registrada em src/preregistration_v2.py
aos eventos de VALIDAÇÃO de daily_k5 (primário) e daily_k6 (só descritivo). A
abertura é registrada em `validation_lock` ANTES de qualquer resultado ser visto;
uma segunda execução é recusada. Escreve reports/fase4b_oos_results.json e
reports/fase4b_relatorio.md.

NÃO rodar sem aprovação explícita do usuário para gastar o out-of-sample.

Uso:
    python -m scripts.run_validation_v2
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import backtest_config as cfg
from src import db
from src import preregistration_v2 as v2
from src.backtest_io import clear_trades, jsonable, load_events, open_validation_lock, save_trades
from src.backtest_v2 import apply_scenario_v2, robustness_checks, simulate_time_exit, summarize_v2, verdict_v2
from src.loaders import load_ohlc


def main() -> None:
    conn = db.connect(config.DB_PATH)
    open_validation_lock(conn, f"v2_{v2.VARIANT}_k{v2.K_PRIMARY}_fade_24h", "abertura única do OOS (Fase 4b)")
    print("Validação aberta (única vez).")
    ohlc = load_ohlc(conn)
    clear_trades(conn, "oos_v2")

    results = {}
    for k in (v2.K_PRIMARY, v2.K_SECONDARY):
        ev = load_events(conn, v2.VARIANT, k, "val")
        gross = simulate_time_exit(ev, ohlc)
        res = {"n_events": len(ev), "scenarios": {}}
        for name, scen in cfg.SCENARIOS.items():
            net = apply_scenario_v2(gross, scen)
            res["scenarios"][name] = summarize_v2(net)
            if name == v2.PRIMARY_SCENARIO:
                res["robustness"] = robustness_checks(net) if len(net) else {}
            save_trades(conn, net, "oos_v2", f"daily_k{k}", name, "val")
        results[f"k{k}"] = res

    primary = results[f"k{v2.K_PRIMARY}"]
    ver, why = verdict_v2(primary["scenarios"][v2.PRIMARY_SCENARIO], primary["robustness"])
    out = {"hypothesis": v2.HYPOTHESIS_H1, "verdict": ver, "reasons": why, "results": results}
    Path("reports/fase4b_oos_results.json").write_text(json.dumps(jsonable(out), indent=1, ensure_ascii=False), encoding="utf-8")

    L = ["# Fase 4b — resultado do out-of-sample (abertura única)\n", f"## Veredito: **{ver.upper()}**\n"]
    L += [f"- {r}" for r in why]
    L.append(f"\nHipótese pré-registrada: {v2.HYPOTHESIS_H1}\n")
    for kk, res in results.items():
        L.append(f"## {kk} ({res['n_events']} eventos de validação)" + (" — PRIMÁRIO" if kk == f"k{v2.K_PRIMARY}" else " — descritivo"))
        for name, s in res["scenarios"].items():
            if s.get("n"):
                L.append(f"- {name}: n={s['n']}, líquido {s['mean_bps']:+.1f} bps (t {s['t']:+.2f}, p unilateral {s['p_one_pos']:.3f}), "
                         f"bruto {s['gross_bps']:+.1f}, hit {s['hit_rate']:.0%}, MAE p95 {s['mae_p95_bps']:.0f} bps, máx {s['mae_max_bps']:.0f} bps")
        rb = res.get("robustness")
        if rb:
            L.append(f"- concentração: {rb['top_pair']} = {rb['top_pair_share']:.0%}; sem ele {rb['mean_bps_without_top_pair']:+.1f} bps; "
                     f"metades {rb['mean_bps_first_half']:+.1f} / {rb['mean_bps_second_half']:+.1f} bps")
        L.append("")
    Path("reports/fase4b_relatorio.md").write_text("\n".join(L), encoding="utf-8")
    print(f"veredito: {ver} — {why}")
    conn.close()


if __name__ == "__main__":
    main()
