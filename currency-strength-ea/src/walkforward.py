"""Walk-forward (Fase 4, item 6): treina 6 meses, testa o mês seguinte, desliza.

Só dentro do período de DESENVOLVIMENTO. Em cada dobra:
  1. recalibra stop/take de CADA configuração só com eventos do treino (a
     calibração da Fase 3 usa o desenvolvimento inteiro — dentro de uma dobra
     isso seria olhar o futuro do treino);
  2. escolhe a configuração pela mesma regra pré-registrada (maior t, cenário
     primário, amostra mínima de treino);
  3. aplica a configuração escolhida aos eventos do mês seguinte, com a
     calibração DAQUELA dobra.
Eventos a menos de `embargo_s` do fim do treino ficam fora da calibração (a
janela de resultado deles invadiria o teste), e a última dobra de teste termina
`embargo_s` antes do corte dev/validação, para a validação continuar intocada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import backtest_config as cfg
from src.backtest import apply_scenario, simulate_trades
from src.calibration import CalibrationParams, apply_calibration, calibrate_stop_take, embargo_seconds
from src.validation_stats import cluster_mean_test, day_clusters


def make_folds(
    dev_start: pd.Timestamp, cutoff: pd.Timestamp, embargo_s: int,
    train_months: int = cfg.WF_TRAIN_MONTHS, test_months: int = cfg.WF_TEST_MONTHS,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Lista de (train_start, train_end, test_end). Dobras começam no 1º dia do mês."""
    start = pd.Timestamp(dev_start).tz_convert("UTC").normalize().replace(day=1)
    folds = []
    while True:
        train_end = start + pd.DateOffset(months=train_months)
        test_end = train_end + pd.DateOffset(months=test_months)
        if test_end + pd.Timedelta(seconds=embargo_s) > cutoff:
            break
        folds.append((start, train_end, test_end))
        start = start + pd.DateOffset(months=test_months)
    return folds


def _evaluate(events: pd.DataFrame, table: pd.DataFrame, ohlc, scenario, horizon: int) -> pd.DataFrame:
    if events.empty:
        return events.assign(net_ret=[], cost_ret=[])
    ev = apply_calibration(events.reset_index(drop=True), table, horizon)
    return apply_scenario(simulate_trades(ev, ohlc, horizon), scenario)


def walk_forward(
    dev_events: dict[str, pd.DataFrame],
    ohlc: dict[str, pd.DataFrame],
    cutoff_ts: int,
    scenario: cfg.Scenario,
    cal: CalibrationParams,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`dev_events`: {config: eventos de desenvolvimento com mfe_z/mae_z}.
    Devolve (dobras, trades_de_teste). `dobras` tem a configuração escolhida,
    t no treino e o resultado do mês de teste."""
    embargo = embargo_seconds(cal)
    all_ts = pd.concat([pd.DatetimeIndex(e["ts"]).to_series() for e in dev_events.values()])
    cutoff = pd.Timestamp(cutoff_ts, unit="s", tz="UTC")
    folds = make_folds(all_ts.min(), cutoff, embargo)

    fold_rows, test_trades = [], []
    for train_start, train_end, test_end in folds:
        train_end_s = int(train_end.timestamp())
        best = None
        tables: dict[str, pd.DataFrame] = {}
        for name, ev in dev_events.items():
            ts = pd.DatetimeIndex(ev["ts"])
            in_train = (ts >= train_start) & (ts + pd.Timedelta(seconds=embargo) <= train_end)
            train = ev[in_train]
            try:
                table = calibrate_stop_take(train, train_end_s, cal)
            except ValueError:
                continue  # eventos insuficientes para calibrar esta configuração nesta dobra
            tables[name] = table
            tr = _evaluate(train, table, ohlc, scenario, cal.horizon)
            if len(tr) < cfg.WF_MIN_TRAIN_TRADES:
                continue
            mt = cluster_mean_test(tr["net_ret"].to_numpy(), day_clusters(tr["ts"]))
            if np.isfinite(mt.t) and (best is None or mt.t > best[1]):
                best = (name, mt.t, mt.n)
        row = {"train_start": train_start, "train_end": train_end, "test_end": test_end,
               "config": best[0] if best else None, "train_t": best[1] if best else np.nan,
               "train_n": best[2] if best else 0, "test_n": 0, "test_mean_bps": np.nan}
        if best:
            ev = dev_events[best[0]]
            ts = pd.DatetimeIndex(ev["ts"])
            test = ev[(ts >= train_end) & (ts < test_end)]
            tr = _evaluate(test, tables[best[0]], ohlc, scenario, cal.horizon)
            if len(tr):
                tr = tr.assign(fold_train_end=train_end, config=best[0])
                test_trades.append(tr)
                row["test_n"] = len(tr)
                row["test_mean_bps"] = float(tr["net_ret"].mean() * 1e4)
        fold_rows.append(row)

    trades = pd.concat(test_trades, ignore_index=True) if test_trades else pd.DataFrame()
    return pd.DataFrame(fold_rows), trades
