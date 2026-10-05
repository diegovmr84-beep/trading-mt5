"""Simulação de trades a partir dos eventos de sinal (Fase 4).

Cada evento vira UM trade: entrada na abertura do candle do sinal, saída no
primeiro de {take, stop, fim do horizonte}. Retornos em log. Custos de
ida-e-volta = (multiplicador do cenário) x spread relativo medido.

Convenções (pré-registradas em src/backtest_config.py):
- stop e take no MESMO candle -> assume-se o stop (conservador; sem dado intra-candle);
- se houver gap (> GAP_THRESHOLD_S) dentro do horizonte, o trade é fechado no
  último candle antes do gap — não se carrega posição por fim de semana;
- stop/take executam no nível exato (sem slippage de gap; o cenário pessimista
  soma slippage ao custo).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest_config import GAP_THRESHOLD_S, HORIZON, MAX_SPREAD_TO_TAKE, Scenario
from src.market_hours import in_rollover


def tradable_mask(events: pd.DataFrame, scenario: Scenario, max_spread_to_take: float = MAX_SPREAD_TO_TAKE) -> np.ndarray:
    """Filtro de pares operáveis reaplicado no cenário: spread escalado pelo
    multiplicador do cenário <= fração do take, e fora do rollover."""
    ts = pd.DatetimeIndex(events["ts"])
    ok = scenario.spread_mult * events["spread_rel"].to_numpy() <= max_spread_to_take * events["take_rel"].to_numpy()
    ok &= ~in_rollover(ts)
    ok &= np.isfinite(events["spread_rel"].to_numpy()) & np.isfinite(events["take_rel"].to_numpy())
    return ok


def simulate_trades(
    events: pd.DataFrame,
    ohlc: dict[str, pd.DataFrame],
    horizon: int = HORIZON,
    gap_threshold_s: int = GAP_THRESHOLD_S,
) -> pd.DataFrame:
    """Retorno BRUTO (antes de custo) de cada evento. `events` precisa ter
    ts, pair, direction, take_rel, stop_rel. Devolve o mesmo índice com
    `exit_reason` ('take'|'stop'|'time'), `bars_held` e `gross_ret`."""
    out = events.copy()
    out["exit_reason"] = None
    out["bars_held"] = np.nan
    out["gross_ret"] = np.nan

    for pair, grp in events.groupby("pair"):
        df = ohlc[pair]
        n = len(df)
        ts_s = df.index.as_unit("s").astype("int64").to_numpy()
        o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
        pos = df.index.get_indexer(pd.DatetimeIndex(grp["ts"]))
        found = pos >= 0
        if not found.any():
            continue
        rows = grp.index[found]
        pos = pos[found]
        d = grp["direction"].to_numpy()[found].astype(float)
        take_rel = grp["take_rel"].to_numpy()[found]
        stop_rel = grp["stop_rel"].to_numpy()[found]

        idx = pos[:, None] + np.arange(horizon)[None, :]
        inb = idx < n
        idx = np.minimum(idx, n - 1)
        step_gap = (ts_s[idx[:, 1:]] - ts_s[idx[:, :-1]]) > gap_threshold_s
        gap_cum = np.concatenate([np.zeros((len(pos), 1), dtype=int), np.cumsum(step_gap, axis=1)], axis=1)
        valid = inb & (gap_cum == 0)  # prefixo contíguo: candle 0 é sempre válido

        entry = o[pos][:, None]
        dd = d[:, None]
        hi = np.where(valid, h[idx], np.nan)
        lo = np.where(valid, l[idx], np.nan)
        take_px = entry * np.exp(dd * take_rel[:, None])
        stop_px = entry * np.exp(-dd * stop_rel[:, None])
        with np.errstate(invalid="ignore"):
            hit_take = np.where(dd > 0, hi >= take_px, lo <= take_px)
            hit_stop = np.where(dd > 0, lo <= stop_px, hi >= stop_px)
        big = horizon
        t_take = np.where(hit_take.any(axis=1), hit_take.argmax(axis=1), big)
        t_stop = np.where(hit_stop.any(axis=1), hit_stop.argmax(axis=1), big)
        stop_first = (t_stop < big) & (t_stop <= t_take)   # empate no mesmo candle -> stop
        take_first = (t_take < big) & (t_take < t_stop)
        last_valid = valid.sum(axis=1) - 1
        close_last = c[idx[np.arange(len(pos)), last_valid]]
        time_ret = d * np.log(close_last / entry[:, 0])

        gross = np.where(stop_first, -stop_rel, np.where(take_first, take_rel, time_ret))
        bars = np.where(stop_first, t_stop + 1, np.where(take_first, t_take + 1, last_valid + 1))
        reason = np.where(stop_first, "stop", np.where(take_first, "take", "time"))
        out.loc[rows, "gross_ret"] = gross
        out.loc[rows, "bars_held"] = bars
        out.loc[rows, "exit_reason"] = reason
    return out


def apply_scenario(trades: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    """Aplica o filtro de spread e o custo do cenário. Devolve só os trades
    operáveis, com `cost_ret` e `net_ret` (retorno líquido, log)."""
    keep = tradable_mask(trades, scenario) & trades["gross_ret"].notna().to_numpy()
    out = trades[keep].copy()
    out["cost_ret"] = scenario.cost_mult * out["spread_rel"]
    out["net_ret"] = out["gross_ret"] - out["cost_ret"]
    out["scenario"] = scenario.name
    return out
