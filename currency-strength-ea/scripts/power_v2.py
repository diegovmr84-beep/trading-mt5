#!/usr/bin/env python3
"""Fase 4b — análise de PODER do teste pré-registrado da v2 (só desenvolvimento).

Pergunta: se o OOS for aberto, qual a chance de ele "validar" H1 mesmo que o
efeito seja real? Reamostra (bootstrap por dia) os trades de DESENVOLVIMENTO de
daily_k5 no tamanho esperado do OOS e aplica TODOS os critérios pré-registrados.
Três mundos: o efeito é o que o desenvolvimento mostrou (limite superior: ele
foi escolhido entre 72 células, então tende a estar inflado — maldição do
vencedor), metade dele, e zero (taxa de falso positivo do protocolo).

Uso:
    python -m scripts.power_v2
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from src import backtest_config as cfg
from src import db
from src import preregistration_v2 as v2
from src.backtest_io import load_events
from src.backtest_v2 import apply_scenario_v2, robustness_checks, simulate_time_exit, summarize_v2, verdict_v2
from src.loaders import load_ohlc
from src.validation_stats import cluster_mean_test, day_clusters


def main(draws: int = 1000, seed: int = 0) -> None:
    conn = db.connect(config.DB_PATH)
    ohlc = load_ohlc(conn)
    dev = apply_scenario_v2(simulate_time_exit(load_events(conn, v2.VARIANT, v2.K_PRIMARY, "dev"), ohlc),
                            cfg.SCENARIOS[v2.PRIMARY_SCENARIO]).reset_index(drop=True)
    n_val = conn.execute("SELECT COUNT(*) FROM signal_candidates WHERE param_set=? AND variant=? AND period='val'",
                         (cfg.param_set_name(v2.K_PRIMARY), v2.VARIANT)).fetchone()[0]
    n_target = int(n_val * len(dev) / len(load_events(conn, v2.VARIANT, v2.K_PRIMARY, "dev")))  # ~ trades após rollover/gap
    conn.close()

    days = pd.DatetimeIndex(dev["ts"]).normalize()
    by_day = {d: g.index.to_numpy() for d, g in dev.groupby(days)}
    day_keys = list(by_day)
    mean_dev = dev["net_ret"].mean()
    rng = np.random.default_rng(seed)
    base = dev["net_ret"].to_numpy()

    rows = []
    for label, shift in (("efeito igual ao do desenvolvimento", 0.0),
                         ("metade do efeito", -0.5 * mean_dev),
                         ("efeito zero (falso positivo)", -mean_dev)):
        verdicts = {"validado": 0, "preliminar": 0, "não validado": 0}
        p_sig = 0
        for _ in range(draws):
            picked = []
            while sum(len(by_day[d]) for d in picked) < n_target:
                picked.append(day_keys[rng.integers(len(day_keys))])
            idx = np.concatenate([by_day[d] for d in picked])
            sample = dev.loc[idx].copy()
            sample["net_ret"] = base[idx] + shift
            sample["ts"] = pd.DatetimeIndex(sample["ts"])  # mantém datas (metades por tempo)
            s = summarize_v2(sample)
            ver, _ = verdict_v2(s, robustness_checks(sample))
            verdicts[ver] += 1
            p_sig += s["p_one_pos"] < v2.OOS_ALPHA
        rows.append((label, shift, verdicts, p_sig / draws))

    L = ["# Fase 4b — poder do teste pré-registrado no OOS (bootstrap só com desenvolvimento)\n"]
    L.append(f"Tamanho esperado do OOS: ~{n_target} trades (daily_k5, cenário {v2.PRIMARY_SCENARIO}). "
             f"Média líquida de desenvolvimento: {mean_dev*1e4:+.1f} bps. {draws} reamostras por dia.\n")
    L.append("| mundo simulado | média líquida verdadeira | p unilateral < 0,05 | validado | preliminar | não validado |")
    L.append("|---|---|---|---|---|---|")
    for label, shift, v, ps in rows:
        L.append(f"| {label} | {(mean_dev + shift)*1e4:+.1f} bps | {ps:.0%} | {v['validado']/draws:.0%} | "
                 f"{v['preliminar']/draws:.0%} | {v['não validado']/draws:.0%} |")
    L.append(
        "\nLeitura: mesmo que o efeito seja **exatamente** o visto no desenvolvimento (cenário otimista para a hipótese, "
        "já que ela foi escolhida entre 72 células), a chance de o teste pré-registrado validá-la é a primeira linha, "
        "coluna \"validado\". Com metade do efeito (o mais provável, pela maldição do vencedor), é ainda menor."
    )
    Path("reports/fase4b_poder_oos.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
