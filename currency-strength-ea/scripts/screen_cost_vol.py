#!/usr/bin/env python3
"""Triagem de custo vs. volatilidade por par, horizonte e sessão (descritivo).

Pergunta: em quais pares e horários o spread deixa de ser o fator dominante?
Usa SÓ custo e volatilidade — nunca retorno de estratégia — e só o período de
desenvolvimento (corte 70/30 de src/split.py). Não gasta OOS e não gera sinal.

Definições (fixadas antes de olhar o resultado):
  - retorno de h candles = log(close[i+h] / close[i]) em janelas contíguas (sem gap/fim de
    semana), com entrada fora do rollover (16h-18h locais de NY);
  - m_h = E|r_h| (movimento típico). Custo de ida-e-volta = 1 spread (como em src/backtest_v2.py);
    cenário realista = 2x o spread medido (o spread da conta Trial é um piso — ver
    src/spread_model.py);
  - razão = (2 x spread) / m_h;  hit mínimo = 0,5 + (custo / m_h) / 2 — a taxa de acerto que uma
    aposta direcional simétrica precisaria só para empatar depois do custo;
  - faixas por razão em 4h: A <= 0,06 · B <= 0,10 · C > 0,10 (mesmas da spread_analysis).
  - estabilidade: correlação de postos (Spearman) entre a razão de cada ano e a razão do período.

Escreve reports/triagem_custo_volatilidade.md e .csv.

Uso:
    python -m scripts.screen_cost_vol
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
from src.pairs import generate_pairs
from src.sessions import classify_session
from src.split import dev_cutoff

HORIZONS = {"1h": 12, "4h": 48, "24h": 288}
COST_MULT = 2.0
TIER_A, TIER_B = 0.06, 0.10
SESSIONS = ["tokyo", "london", "london_ny_overlap", "ny", "other"]
H_SESSION = 12
_HOUR_SESSION = {h: classify_session(pd.Timestamp(2024, 1, 3, h, tz="UTC").to_pydatetime()) for h in range(24)}


def _pip(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def spread_bps_by_pair(conn) -> pd.Series:
    sp = pd.read_sql_query(
        "SELECT s.name AS pair, ss.ts_utc, (ss.ask - ss.bid) / ((ss.ask + ss.bid) / 2.0) AS rel "
        "FROM spread_samples ss JOIN symbols s ON s.id = ss.symbol_id WHERE ss.bid > 0 AND ss.ask > 0",
        conn,
    )
    idx = pd.DatetimeIndex(pd.to_datetime(sp["ts_utc"], unit="s", utc=True))
    keep = ~(market_closed(idx) | in_rollover(idx))
    return sp[keep].groupby("pair")["rel"].median() * 1e4


def horizon_returns(df: pd.DataFrame, h: int) -> pd.DataFrame:
    """Retornos log de h candles com entrada fora do rollover e janela contígua."""
    ts = df.index.as_unit("s").astype("int64").to_numpy()
    c = df["close"].to_numpy()
    n = len(c)
    ok = np.zeros(n, dtype=bool)
    ok[: n - h] = (ts[h:] - ts[: n - h]) == h * 300
    r = np.full(n, np.nan)
    r[: n - h] = np.log(c[h:] / c[: n - h])
    entry = df.index
    ok &= ~in_rollover(entry)
    return pd.DataFrame({"r": np.where(ok, r, np.nan)}, index=entry).dropna()


def be_hit(cost_bps: float, m_bps: float) -> float:
    return 0.5 + (cost_bps / m_bps) / 2


def main() -> None:
    conn = db.connect(config.DB_PATH)
    ts_min, ts_max = conn.execute("SELECT MIN(ts_utc), MAX(ts_utc) FROM candles_m5").fetchone()
    cutoff = dev_cutoff(ts_min, ts_max)
    spread = spread_bps_by_pair(conn)

    rows, sess_rows, year_ratio = [], [], {}
    for pair in generate_pairs():
        d = pd.read_sql_query(
            "SELECT c.ts_utc, c.open, c.high, c.low, c.close FROM candles_m5 c JOIN symbols s ON s.id = c.symbol_id "
            "WHERE s.name = ? AND c.ts_utc < ? ORDER BY c.ts_utc",
            conn, params=(pair, cutoff),
        )
        d.index = pd.DatetimeIndex(pd.to_datetime(d.pop("ts_utc"), unit="s", utc=True))
        sp_bps = float(spread[pair])
        cost = COST_MULT * sp_bps
        row = {"pair": pair, "spread_pips": sp_bps * 1e-4 * float(d["close"].median()) / _pip(pair), "spread_bps": sp_bps}
        for name, h in HORIZONS.items():
            r = horizon_returns(d, h)["r"]
            m = r.abs().mean() * 1e4
            row[f"m_{name}_bps"] = m
            row[f"ratio_{name}"] = cost / m
            row[f"hit_min_{name}"] = be_hit(cost, m)
            if name == "4h":
                yr = (r.abs() * 1e4).groupby(r.index.year).mean()
                year_ratio[pair] = cost / yr
            if name == "1h":
                hr = (r.abs() * 1e4).groupby(r.index.hour).mean()
                for hour, mm in hr.items():
                    sess_rows.append({"pair": pair, "hour": hour, "m_bps": mm, "n": int((r.index.hour == hour).sum())})
        rows.append(row)

    t = pd.DataFrame(rows).sort_values("ratio_4h").reset_index(drop=True)
    t["faixa"] = np.where(t.ratio_4h <= TIER_A, "A", np.where(t.ratio_4h <= TIER_B, "B", "C"))

    yr = pd.DataFrame(year_ratio).T  # pares x anos
    overall = t.set_index("pair")["ratio_4h"]
    stab = {y: yr[y].dropna().rank().corr(overall.loc[yr[y].dropna().index].rank()) for y in yr.columns}

    hs = pd.DataFrame(sess_rows)
    hs["session"] = hs["hour"].map(_HOUR_SESSION)
    # movimento médio de 1h por sessão e par (ponderado por n) e razão com custo do par
    hs["w"] = hs["m_bps"] * hs["n"]
    ps = hs.groupby(["pair", "session"]).agg(w=("w", "sum"), n=("n", "sum"))
    ps["m_bps"] = ps["w"] / ps["n"]
    ps = ps["m_bps"].unstack("session")[SESSIONS]
    sess_ratio = ps.rdiv(COST_MULT * t.set_index("pair")["spread_bps"], axis=0)
    hour_pool = hs.groupby("hour").apply(lambda g: np.average(g["m_bps"], weights=g["n"]))

    out = ["# Triagem de custo vs. volatilidade (descritivo, só desenvolvimento)\n"]
    out.append(
        f"Período: até {pd.Timestamp(cutoff, unit='s', tz='UTC'):%Y-%m-%d}. Só custo e volatilidade; nenhum retorno de "
        "estratégia, nenhum OOS. Custo realista = 2× o spread medido (piso da conta Trial; em conta real pode ser maior). "
        "Retorno de h candles em janelas contíguas, entrada fora do rollover.\n"
    )
    out.append(
        "**Como ler:** `razão` = custo ÷ movimento típico. `hit mín` = taxa de acerto que uma aposta direcional "
        "simétrica precisaria só para empatar depois do custo. Razão baixa = o custo pesa pouco; "
        "**não** significa que há edge — só que, se houver, o custo não o come.\n"
    )
    out.append("## Por par (ordenado pela razão em 4h)\n")
    out.append("| par | faixa | spread (bps) | mov. 1h (bps) | mov. 4h (bps) | mov. 24h (bps) | razão 1h | razão 4h | razão 24h | hit mín 1h | hit mín 4h | hit mín 24h |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in t.itertuples():
        out.append(
            f"| {r.pair} | {r.faixa} | {r.spread_bps:.2f} | {r.m_1h_bps:.1f} | {r.m_4h_bps:.1f} | {r.m_24h_bps:.1f} | "
            f"{r.ratio_1h:.3f} | {r.ratio_4h:.3f} | {r.ratio_24h:.3f} | {r.hit_min_1h:.1%} | {r.hit_min_4h:.1%} | {r.hit_min_24h:.1%} |"
        )
    cnt = t.faixa.value_counts().to_dict()
    out.append(f"\nFaixas (razão 4h): A (≤ {TIER_A}) = {cnt.get('A', 0)} · B (≤ {TIER_B}) = {cnt.get('B', 0)} · C = {cnt.get('C', 0)}.")
    out.append(
        "**Aviso:** os cortes 0,06/0,10 foram herdados da `spread_analysis` (custo de 1× spread sobre um take de "
        "0,9·sigma·√36); aqui o custo é 2× e o denominador é outro, então quase tudo cai na faixa C e as faixas "
        "não discriminam. Use a **ordem** dos pares e as colunas `hit mín`, não as letras.\n"
    )

    out.append("## Razão por horizonte (mediana dos 28 pares)\n")
    out.append("| horizonte | razão mediana | hit mín mediano |")
    out.append("|---|---|---|")
    for name in HORIZONS:
        out.append(f"| {name} | {t[f'ratio_{name}'].median():.3f} | {t[f'hit_min_{name}'].median():.1%} |")
    out.append("")

    out.append("## Movimento típico de 1h por sessão (bps) e razão custo/movimento\n")
    out.append("Sessões em UTC fixo (sem ajuste de horário de verão). Spread da Trial é constante entre sessões, então a razão varia só pelo movimento.\n")
    out.append("| par | " + " | ".join(SESSIONS) + " | melhor sessão (razão) |")
    out.append("|---|" + "---|" * (len(SESSIONS) + 1))
    for pair in t["pair"]:
        cells = " | ".join(f"{ps.loc[pair, s]:.1f} ({sess_ratio.loc[pair, s]:.2f})" for s in SESSIONS)
        out.append(f"| {pair} | {cells} | {sess_ratio.loc[pair].idxmin()} |")
    out.append("")

    out.append("## Movimento médio de 1h por hora UTC de entrada (28 pares)\n")
    out.append("| hora UTC | mov. 1h (bps) |")
    out.append("|---|---|")
    for h, v in hour_pool.items():
        out.append(f"| {h:02d} | {v:.2f} |")
    out.append("")

    out.append("## Estabilidade da triagem no tempo\n")
    out.append("Correlação de postos entre a razão (4h) de cada ano e a do período inteiro — alta = a ordem dos pares é estável, não efeito de um regime.\n")
    out.append("| ano | correlação de postos |")
    out.append("|---|---|")
    for y, c in stab.items():
        out.append(f"| {y} | {c:.2f} |")
    out.append("")

    Path("reports/triagem_custo_volatilidade.md").write_text("\n".join(out), encoding="utf-8")
    t.to_csv("reports/triagem_custo_volatilidade.csv", index=False)
    print("\n".join(out))
    conn.close()


if __name__ == "__main__":
    main()
