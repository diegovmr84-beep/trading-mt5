"""Carga de eventos de sinal e gravação de trades da Fase 4."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import backtest_config as cfg

EVENT_COLS = [
    "ts_utc", "pair", "direction", "strong_ccy", "weak_ccy", "z_pair", "sigma1",
    "take_rel", "stop_rel", "spread_rel", "period",
]


def config_id(variant: str, k: int) -> str:
    return f"{variant}_k{k}"


def configs() -> list[tuple[str, int]]:
    return [(v, k) for v in cfg.VARIANTS for k in cfg.K_MIN_GRID]


def load_events(conn, variant: str, k: int, period: str) -> pd.DataFrame:
    """Eventos de UM período ('dev' ou 'val') de uma configuração. O período é
    sempre pedido de forma explícita — não existe leitura "de tudo"."""
    if period not in ("dev", "val"):
        raise ValueError("period deve ser 'dev' ou 'val' (embargo nunca entra em backtest)")
    df = pd.read_sql_query(
        f"SELECT {', '.join(EVENT_COLS)} FROM signal_candidates "
        "WHERE param_set = ? AND variant = ? AND period = ? ORDER BY ts_utc, pair",
        conn,
        params=(cfg.param_set_name(k), variant, period),
    )
    df["ts"] = pd.DatetimeIndex(pd.to_datetime(df.pop("ts_utc"), unit="s", utc=True))
    return df


def save_trades(conn, trades: pd.DataFrame, run: str, config: str, scenario: str, period: str) -> int:
    if trades.empty:
        return 0
    out = pd.DataFrame(
        {
            "run": run,
            "config": config,
            "scenario": scenario,
            "period": period,
            "ts_utc": pd.DatetimeIndex(trades["ts"]).as_unit("s").astype("int64").to_numpy(),
            "pair": trades["pair"].to_numpy(),
            "direction": trades["direction"].to_numpy(),
            "strong_ccy": trades["strong_ccy"].to_numpy(),
            "weak_ccy": trades["weak_ccy"].to_numpy(),
            "take_rel": trades["take_rel"].to_numpy(),
            "stop_rel": trades["stop_rel"].to_numpy(),
            "exit_reason": trades["exit_reason"].to_numpy(),
            "bars_held": trades["bars_held"].to_numpy(),
            "gross_ret": trades["gross_ret"].to_numpy(),
            "cost_ret": trades["cost_ret"].to_numpy(),
            "net_ret": trades["net_ret"].to_numpy(),
        }
    )
    out.to_sql("backtest_trades", conn, if_exists="append", index=False)
    conn.commit()
    return len(out)


def clear_trades(conn, run: str, config: str | None = None) -> None:
    if config is None:
        conn.execute("DELETE FROM backtest_trades WHERE run = ?", (run,))
    else:
        conn.execute("DELETE FROM backtest_trades WHERE run = ? AND config = ?", (run, config))
    conn.commit()


class ValidationAlreadyOpenedError(RuntimeError):
    """O período de validação (out-of-sample) só pode ser aberto uma vez."""


def open_validation_lock(conn, config_name: str, note: str = "") -> None:
    """Registra a abertura da validação ANTES de olhar qualquer resultado dela.
    Recusa se já houver registro: reabrir o OOS depois de ajustar algo
    transforma o out-of-sample em mais um conjunto de desenvolvimento."""
    row = conn.execute("SELECT opened_at, config FROM validation_lock LIMIT 1").fetchone()
    if row:
        raise ValidationAlreadyOpenedError(
            f"validação já aberta em {row[0]} (config {row[1]}) — não pode ser reaberta"
        )
    conn.execute(
        "INSERT INTO validation_lock (opened_at, config, note) VALUES (datetime('now'), ?, ?)",
        (config_name, note),
    )
    conn.commit()


def jsonable(obj):
    """Converte numpy/pandas em tipos nativos para json.dump."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj
