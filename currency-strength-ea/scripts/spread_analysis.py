#!/usr/bin/env python3
"""Operabilidade por par: quanto o spread da Exness consome do movimento esperado.

Critério (definido ANTES de olhar qualquer resultado de backtest, e só com
custo — nunca com retorno): razão custo/take = spread relativo "normal" do par
(mercado aberto, fora do rollover) dividido pelo take típico (0,9 · sigma1 ·
sqrt(36), com sigma1 = volatilidade por candle M5 do par SÓ no período de
desenvolvimento; 0,9 = ordem de grandeza do take calibrado na Fase 3).

    Faixa A: custo/take <= 0,06   Faixa B: 0,06-0,10   Faixa C: > 0,10

Escreve reports/spread_operabilidade.md.

Uso:
    python -m scripts.spread_analysis
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from src import db
from src.market_hours import in_rollover, market_closed
from src.split import dev_cutoff

TIER_A, TIER_B = 0.06, 0.10
HORIZON = 36
TAKE_Z = 0.9


def _pip(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def main() -> None:
    conn = db.connect(config.DB_PATH)
    sp = pd.read_sql_query(
        "SELECT s.name AS pair, ss.ts_utc, ss.bid, ss.ask FROM spread_samples ss "
        "JOIN symbols s ON s.id = ss.symbol_id WHERE ss.bid > 0 AND ss.ask > 0",
        conn,
    )
    idx = pd.DatetimeIndex(pd.to_datetime(sp["ts_utc"], unit="s", utc=True))
    sp["closed"], sp["roll"] = market_closed(idx), in_rollover(idx)
    sp["pips"] = (sp["ask"] - sp["bid"]) / sp["pair"].map(_pip)
    sp["rel"] = (sp["ask"] - sp["bid"]) / ((sp["ask"] + sp["bid"]) / 2)

    normal = sp[~sp.closed & ~sp.roll]
    roll_open = sp[~sp.closed & sp.roll]
    n_total = len(sp)

    ts_min, ts_max = conn.execute("SELECT MIN(ts_utc), MAX(ts_utc) FROM candles_m5").fetchone()
    cutoff = dev_cutoff(ts_min, ts_max)

    rows = []
    for pair, g in normal.groupby("pair"):
        d = pd.read_sql_query(
            "SELECT c.ts_utc, c.close FROM candles_m5 c JOIN symbols s ON s.id = c.symbol_id "
            "WHERE s.name = ? AND c.ts_utc < ? ORDER BY c.ts_utc",
            conn, params=(pair, cutoff),
        )
        lr = np.log(d["close"]).diff().where(d["ts_utc"].diff() <= 600)  # fora retornos que cruzam gap
        take = TAKE_Z * lr.std() * np.sqrt(HORIZON)
        rel = g["rel"].median()
        r = roll_open[roll_open.pair == pair]
        rows.append(
            {
                "pair": pair,
                "spread_pips": g["pips"].median(),
                "spread_bps": rel * 1e4,
                "take_bps": take * 1e4,
                "custo_take": rel / take,
                "rollover_pips_p95": r["pips"].quantile(0.95) if len(r) else np.nan,
                "rollover_pips_max": r["pips"].max() if len(r) else np.nan,
            }
        )
    t = pd.DataFrame(rows).sort_values("custo_take").reset_index(drop=True)
    t["faixa"] = np.where(t.custo_take <= TIER_A, "A", np.where(t.custo_take <= TIER_B, "B", "C"))

    ev = pd.read_sql_query("SELECT pair, ts_utc FROM signal_candidates", conn)
    ev_idx = pd.DatetimeIndex(pd.to_datetime(ev["ts_utc"], unit="s", utc=True))
    roll_share = in_rollover(ev_idx).mean() if len(ev) else float("nan")
    flat = normal.groupby(["pair", normal["ts_utc"].map(lambda x: pd.Timestamp(x, unit="s", tz="UTC").hour)])["pips"].median()
    max_hourly_var = (flat.groupby("pair").max() / flat.groupby("pair").min()).max()

    lines = ["# Operabilidade por par — spread da Exness Trial vs. movimento esperado\n"]
    lines.append(
        f"Amostras de spread: {n_total:,}. **{sp.closed.mean():.1%} foram gravadas com o mercado fechado** "
        "(sáb/dom, cotação congelada) e foram descartadas; amostras no rollover (16h-19h de NY) "
        "ficam fora do spread \"normal\" e são tratadas à parte.\n"
    )
    lines.append("## Achados\n")
    lines.append(
        f"1. **Fora do rollover, o spread de cada par é constante ao longo do dia** (razão máx/mín entre "
        f"horas, no pior par: {max_hourly_var:.2f}×). Uma conta real varia entre Tóquio/Londres/NY; "
        "isto indica spread fixo/simulado da conta Trial. **Os números abaixo são um piso de custo, "
        "não uma estimativa do spread real de execução.**"
    )
    lines.append(
        "2. **O spread largo que aparece no bid/ask bruto vem do rollover e do fim de semana**, não do "
        "spread normal dos pares (ver colunas de rollover)."
    )
    lines.append(
        f"3. {roll_share:.1%} dos eventos de sinal da Fase 3 caem no rollover — nunca operáveis.\n"
    )
    lines.append("## Custo vs. movimento esperado (só período de desenvolvimento para a volatilidade)\n")
    lines.append("| par | faixa | spread (pips) | spread (bps) | take típico (bps) | custo/take | rollover p95 (pips) | rollover máx (pips) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in t.itertuples():
        lines.append(
            f"| {r.pair} | {r.faixa} | {r.spread_pips:.1f} | {r.spread_bps:.2f} | {r.take_bps:.1f} | "
            f"{r.custo_take:.3f} | {r.rollover_pips_p95:.1f} | {r.rollover_pips_max:.1f} |"
        )
    cnt = t.faixa.value_counts().to_dict()
    lines.append(
        f"\nFaixas: A (custo/take ≤ {TIER_A}) = {cnt.get('A', 0)} pares · B ({TIER_A}-{TIER_B}) = "
        f"{cnt.get('B', 0)} · C (> {TIER_B}) = {cnt.get('C', 0)}. Os pares da faixa C são os de baixa "
        "volatilidade e/ou spread relativo alto (cruzados com NZD e CHF) — o que a Seção 5 do estudo antecipou."
    )
    out = Path("reports/spread_operabilidade.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"escrito: {out}")
    print(t[["pair", "faixa", "spread_pips", "custo_take"]].round(3).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
