#!/usr/bin/env python3
"""Fase 4b — perfil DESCRITIVO da v2 no desenvolvimento (fade de daily, saída em 24h).

NÃO é evidência: a hipótese nasceu destes mesmos dados, escolhida entre 72
células. Serve para dimensionar o que se espera (retorno, hit rate) e,
principalmente, o RISCO de segurar 24h sem stop (pior excursão adversa).
Só lê eventos de desenvolvimento.

Uso:
    python -m scripts.run_v2_dev
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import backtest_config as cfg
from src import db
from src import preregistration_v2 as v2
from src.backtest_io import load_events
from src.backtest_v2 import apply_scenario_v2, robustness_checks, simulate_time_exit, summarize_v2
from src.loaders import load_ohlc


def main() -> None:
    conn = db.connect(config.DB_PATH)
    ohlc = load_ohlc(conn)
    L = ["# Fase 4b — perfil descritivo da v2 no desenvolvimento (NÃO é evidência)\n"]
    L.append(
        "Fade de sinais `daily`, entrada na abertura, saída por tempo em 24h, sem stop. **A hipótese foi "
        "formada nestes mesmos dados (escolhida entre 72 células), então estes números são otimistas por "
        "construção** — só o out-of-sample intocado pode confirmar. O que este perfil acrescenta de "
        "verdade é o **risco**: a pior excursão adversa (MAE) de segurar 24h sem proteção.\n"
    )
    for k in (v2.K_PRIMARY, v2.K_SECONDARY):
        ev = load_events(conn, v2.VARIANT, k, "dev")
        gross = simulate_time_exit(ev, ohlc)
        L.append(f"## daily_k{k} ({len(ev)} eventos de desenvolvimento)\n")
        L.append("| cenário | n | bruto (bps) | líquido (bps) | mediana líq. (bps) | t | hit rate | MAE mediano / p95 / máx (bps) |")
        L.append("|---|---|---|---|---|---|---|---|")
        for name, scen in cfg.SCENARIOS.items():
            s = summarize_v2(apply_scenario_v2(gross, scen))
            L.append(
                f"| {name} | {s['n']} | {s['gross_bps']:+.1f} | {s['mean_bps']:+.1f} | {s['median_bps']:+.1f} | "
                f"{s['t']:+.2f} | {s['hit_rate']:.0%} | {s['mae_p50_bps']:.0f} / {s['mae_p95_bps']:.0f} / {s['mae_max_bps']:.0f} |"
            )
            if name == v2.PRIMARY_SCENARIO:
                rob = robustness_checks(apply_scenario_v2(gross, scen))
        L.append(
            f"\nConcentração (realista): par mais frequente **{rob['top_pair']}** = {rob['top_pair_share']:.0%} dos trades; "
            f"média líquida sem ele {rob['mean_bps_without_top_pair']:+.1f} bps; 1ª metade {rob['mean_bps_first_half']:+.1f}, "
            f"2ª metade {rob['mean_bps_second_half']:+.1f} bps.\n"
        )
    Path("reports/fase4b_v2_dev_descritivo.md").write_text("\n".join(L), encoding="utf-8")
    print("escrito reports/fase4b_v2_dev_descritivo.md")
    conn.close()


if __name__ == "__main__":
    main()
