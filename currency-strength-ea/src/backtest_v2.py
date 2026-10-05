"""Simulação e veredito da v2 (Fase 4b): fade do sinal, saída por tempo em 24h.

Regras em src/preregistration_v2.py (fixadas antes do OOS). Cada evento vira UM
trade CONTRA a direção do sinal; entrada na abertura do candle do sinal; saída
no fechamento do 288º candle (ou do último candle antes de um gap — não se
carrega posição por fim de semana). Sem stop/take: por isso registra-se a pior
excursão adversa (MAE) de cada trade, que é o risco real de segurar 24h sem
proteção e entra no relatório mesmo que o veredito seja só de expectativa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import backtest_config as cfg
from src import preregistration_v2 as v2
from src.market_hours import in_rollover
from src.validation_stats import cluster_mean_test, day_clusters


def simulate_time_exit(
    events: pd.DataFrame,
    ohlc: dict[str, pd.DataFrame],
    horizon: int = v2.HORIZON_CANDLES,
    fade: bool = True,
    gap_threshold_s: int = cfg.GAP_THRESHOLD_S,
) -> pd.DataFrame:
    """Retorno BRUTO log de cada evento na direção da posição (contra o sinal
    se `fade`). Acrescenta `gross_ret`, `bars_held`, `exit_reason`
    ('time' = horizonte inteiro, 'gap' = fechado antes de um gap/fim dos dados)
    e `mae` (pior excursão adversa, log >= 0)."""
    out = events.copy()
    out["gross_ret"] = np.nan
    out["bars_held"] = np.nan
    out["exit_reason"] = None
    out["mae"] = np.nan
    for pair, grp in events.groupby("pair"):
        df = ohlc[pair]
        n = len(df)
        ts_s = df.index.as_unit("s").astype("int64").to_numpy()
        o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
        pos = df.index.get_indexer(pd.DatetimeIndex(grp["ts"]))
        ok = pos >= 0
        if not ok.any():
            continue
        rows, pos = grp.index[ok], pos[ok]
        sig = grp["direction"].to_numpy()[ok].astype(float)
        d = -sig if fade else sig

        idx = pos[:, None] + np.arange(horizon)[None, :]
        inb = idx < n
        idx = np.minimum(idx, n - 1)
        step_gap = (ts_s[idx[:, 1:]] - ts_s[idx[:, :-1]]) > gap_threshold_s
        gap_cum = np.concatenate([np.zeros((len(pos), 1), dtype=int), np.cumsum(step_gap, axis=1)], axis=1)
        valid = inb & (gap_cum == 0)
        last = valid.sum(axis=1) - 1
        entry = o[pos]
        close_last = c[idx[np.arange(len(pos)), last]]
        hi = np.where(valid, h[idx], -np.inf).max(axis=1)
        lo = np.where(valid, l[idx], np.inf).min(axis=1)
        adverse = np.where(d > 0, np.log(entry / lo), np.log(hi / entry))

        out.loc[rows, "gross_ret"] = d * np.log(close_last / entry)
        out.loc[rows, "bars_held"] = last + 1
        out.loc[rows, "exit_reason"] = np.where(last + 1 == horizon, "time", "gap")
        out.loc[rows, "mae"] = np.maximum(adverse, 0.0)
    return out


def apply_scenario_v2(trades: pd.DataFrame, scenario: cfg.Scenario) -> pd.DataFrame:
    """Exclui rollover e eventos sem spread medido; aplica o custo do cenário
    (multiplicador x spread relativo; ida-e-volta = 1 spread)."""
    ts = pd.DatetimeIndex(trades["ts"])
    keep = ~in_rollover(ts) & np.isfinite(trades["spread_rel"].to_numpy()) & trades["gross_ret"].notna().to_numpy()
    out = trades[keep].copy()
    out["cost_ret"] = scenario.cost_mult * out["spread_rel"]
    out["net_ret"] = out["gross_ret"] - out["cost_ret"]
    out["scenario"] = scenario.name
    return out


def summarize_v2(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n": 0}
    mt = cluster_mean_test(trades["net_ret"].to_numpy(), day_clusters(trades["ts"]))
    return {
        "n": mt.n,
        "n_clusters": mt.n_clusters,
        "mean_bps": mt.mean * 1e4,
        "median_bps": float(trades["net_ret"].median() * 1e4),
        "t": mt.t,
        "p_one_pos": mt.p_one_pos,
        "hit_rate": float((trades["net_ret"] > 0).mean()),
        "gross_bps": float(trades["gross_ret"].mean() * 1e4),
        "mae_p50_bps": float(trades["mae"].median() * 1e4),
        "mae_p95_bps": float(trades["mae"].quantile(0.95) * 1e4),
        "mae_max_bps": float(trades["mae"].max() * 1e4),
    }


def robustness_checks(trades: pd.DataFrame) -> dict:
    """Concentração e estabilidade pré-registradas: média líquida sem o par mais
    frequente, e média líquida em cada metade (no tempo) da amostra."""
    top = trades["pair"].value_counts().index[0]
    rest = trades[trades["pair"] != top]
    ts = pd.DatetimeIndex(trades["ts"])
    mid = ts.min() + (ts.max() - ts.min()) / 2
    first, second = trades[ts < mid], trades[ts >= mid]
    return {
        "top_pair": top,
        "top_pair_share": float((trades["pair"] == top).mean()),
        "mean_bps_without_top_pair": float(rest["net_ret"].mean() * 1e4) if len(rest) else float("nan"),
        "mean_bps_first_half": float(first["net_ret"].mean() * 1e4) if len(first) else float("nan"),
        "mean_bps_second_half": float(second["net_ret"].mean() * 1e4) if len(second) else float("nan"),
    }


def verdict_v2(oos: dict, rob: dict) -> tuple[str, list[str]]:
    """Veredito pré-registrado (src/preregistration_v2.py). `oos` = summarize_v2 do
    cenário realista; `rob` = robustness_checks dos mesmos trades."""
    if not oos or oos.get("n", 0) == 0:
        return "não validado", ["sem trades no OOS"]
    if oos["mean_bps"] <= 0:
        return "não validado", [f"expectativa líquida no OOS <= 0 ({oos['mean_bps']:.1f} bps)"]
    checks = {
        "significância unilateral (p < 0,05)": oos["p_one_pos"] < v2.OOS_ALPHA,
        f"amostra mínima (n >= {v2.N_MIN_TRADES})": oos["n"] >= v2.N_MIN_TRADES,
        f"efeito mínimo (>= {v2.MIN_EFFECT_BPS} bps líquidos)": oos["mean_bps"] >= v2.MIN_EFFECT_BPS,
        "sem o par mais frequente a média segue > 0": (not v2.REQUIRE_LEAVE_TOP_PAIR_OUT_POSITIVE)
        or bool(rob["mean_bps_without_top_pair"] > 0),
        "as duas metades do OOS com média > 0": (not v2.REQUIRE_BOTH_HALVES_POSITIVE)
        or bool(rob["mean_bps_first_half"] > 0 and rob["mean_bps_second_half"] > 0),
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return "validado", ["todos os critérios pré-registrados atendidos"]
    return "preliminar", [f"falhou: {k}" for k in failed]
