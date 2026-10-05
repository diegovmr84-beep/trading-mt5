#!/usr/bin/env python3
"""Fase 4b — robustez da hipótese de reversão na janela `daily` (SÓ desenvolvimento).

Hipótese formada no estudo de eventos (reports/fase4b_event_study_dev.md): sinais
da janela `daily` (k >= 5) são seguidos de REVERSÃO em ~24h. Este script não a
confirma (a hipótese nasceu destes mesmos dados, escolhida entre 72 células; só
o out-of-sample intocado pode confirmar) — apenas verifica se ela é frágil:
  - aparece nas duas metades do período de desenvolvimento, com o mesmo sinal?
  - sobrevive sem os maiores outliers (mediana, média aparada, sem mar/2020)?
  - depende de um par só (leave-one-pair-out)?

Um "não" em qualquer um desses é motivo para NÃO gastar o OOS nela.

Uso:
    python -m scripts.robustness_daily_reversal_dev
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy import stats

import config
from scripts.event_study_dev import event_returns
from src import db
from src.backtest_io import load_events
from src.loaders import load_ohlc
from src.market_hours import in_rollover
from src.validation_stats import cluster_mean_test, day_clusters

H = "r288"  # 24h


def fmt(r, cl, spread):
    mt = cluster_mean_test(r, cl)
    net = cluster_mean_test(r - spread, cl)
    return mt, net


def main() -> None:
    conn = db.connect(config.DB_PATH)
    ohlc = load_ohlc(conn)
    out = ["# Fase 4b — robustez da reversão na janela `daily` (só desenvolvimento, exploratório)\n"]
    out.append(
        "Retorno em 24h **na direção do sinal** (negativo = reversão), bruto, em bps; t por cluster de dia. "
        "Hipótese formada nestes mesmos dados → só o OOS intocado pode confirmar; isto só mede fragilidade.\n"
    )
    for k in (5, 6):
        ev = load_events(conn, "daily", k, "dev").reset_index(drop=True)
        ev = ev[~in_rollover(pd.DatetimeIndex(ev["ts"])) & np.isfinite(ev["spread_rel"])].reset_index(drop=True)
        ev[H] = event_returns(ev, ohlc)[H]
        ev = ev.dropna(subset=[H]).reset_index(drop=True)
        r, cl, sp = ev[H].to_numpy(), day_clusters(ev["ts"]), ev["spread_rel"].to_numpy()
        ts = pd.DatetimeIndex(ev["ts"])

        out.append(f"## daily_k{k} (n={len(ev)})\n")
        mt, _ = fmt(r, cl, sp)
        out.append(f"- Todos: média **{mt.mean*1e4:+.1f} bps** (t {mt.t:+.2f}), mediana {np.median(r)*1e4:+.1f} bps, "
                   f"% eventos com reversão: {(r < 0).mean():.0%}")
        lo, hi = np.quantile(r, [0.05, 0.95])
        trimmed = r[(r >= lo) & (r <= hi)]
        out.append(f"- Aparada 5%/95%: média {trimmed.mean()*1e4:+.1f} bps")
        no2020 = ~((ts.year == 2020) & (ts.month == 3))
        mt2, _ = fmt(r[no2020], cl[no2020], sp[no2020])
        out.append(f"- Sem março/2020: média {mt2.mean*1e4:+.1f} bps (t {mt2.t:+.2f}, n={mt2.n})")

        mid = ts.min() + (ts.max() - ts.min()) / 2
        for name, mask in (("1ª metade do dev", ts < mid), ("2ª metade do dev", ts >= mid)):
            m, _ = fmt(r[mask], cl[mask], sp[mask])
            out.append(f"- {name} ({mid.date() if name.startswith('1') else ts.max().date()} fim): média {m.mean*1e4:+.1f} bps (t {m.t:+.2f}, n={m.n})")

        yearly = pd.Series(r, index=ts).groupby(ts.year).agg(["mean", "size"])
        out.append("- Por ano (bps): " + ", ".join(f"{y}: {row['mean']*1e4:+.0f} (n={int(row['size'])})" for y, row in yearly.iterrows()))

        pairs = ev["pair"].to_numpy()
        worst = []
        for p in np.unique(pairs):
            m, _ = fmt(r[pairs != p], cl[pairs != p], sp[pairs != p])
            worst.append((m.mean * 1e4, p))
        worst.sort(reverse=True)  # menos negativo = a exclusão que mais enfraquece o efeito
        out.append(f"- Leave-one-pair-out: média varia de {min(w[0] for w in worst):+.1f} a {max(w[0] for w in worst):+.1f} bps "
                   f"(a que mais enfraquece: sem {worst[0][1]} → {worst[0][0]:+.1f})")
        share = pd.Series(pairs).value_counts(normalize=True).head(3)
        out.append("- Pares com mais eventos: " + ", ".join(f"{p} {s:.0%}" for p, s in share.items()) + "\n")

    Path("reports/fase4b_robustez_daily_dev.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    conn.close()


if __name__ == "__main__":
    main()
