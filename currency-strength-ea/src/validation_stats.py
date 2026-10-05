"""Estatística de validação da Fase 4: teste robusto a cluster, Bonferroni,
expectativa em R e lógica do veredicto (regras em src/backtest_config.py)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from src import backtest_config as cfg


@dataclass(frozen=True)
class MeanTest:
    n: int
    n_clusters: int
    mean: float
    se: float
    t: float
    p_two: float
    p_one_pos: float   # H1: média > 0


def cluster_mean_test(returns: np.ndarray, clusters: np.ndarray) -> MeanTest:
    """Teste t da média com erro-padrão robusto a cluster (CR0 com correção
    G/(G-1); t com G-1 graus de liberdade). Os trades de um mesmo cluster não
    são independentes (choques comuns, moedas em comum, sobreposição no tempo);
    tratar cada trade como amostra i.i.d. infla a significância (Seção 4 do estudo)."""
    r = np.asarray(returns, dtype=float)
    keep = np.isfinite(r)
    r, cl = r[keep], np.asarray(clusters)[keep]
    n = len(r)
    if n < 2:
        return MeanTest(n, 0, float(r.mean()) if n else np.nan, np.nan, np.nan, np.nan, np.nan)
    m = r.mean()
    codes, uniq = pd.factorize(cl)
    g = len(uniq)
    cluster_sums = np.bincount(codes, weights=r - m)
    if g < 2:
        return MeanTest(n, g, float(m), np.nan, np.nan, np.nan, np.nan)
    se = np.sqrt(g / (g - 1) * np.sum(cluster_sums**2)) / n
    if se == 0:
        return MeanTest(n, g, float(m), 0.0, np.inf if m > 0 else -np.inf, 0.0, 0.0 if m > 0 else 1.0)
    t = m / se
    df = g - 1
    return MeanTest(
        n, g, float(m), float(se), float(t),
        float(2 * stats.t.sf(abs(t), df)), float(stats.t.sf(t, df)),
    )


def day_clusters(ts: pd.Series) -> np.ndarray:
    """Cluster = dia UTC do trade (captura choques macro comuns e a sobreposição
    de trades simultâneos no mesmo dia)."""
    return pd.DatetimeIndex(ts).normalize().to_numpy()


def expectancy_r(net: np.ndarray, stop_rel: np.ndarray) -> float:
    """Expectativa líquida em múltiplos de R (R = stop médio dos trades)."""
    net, stop = np.asarray(net, float), np.asarray(stop_rel, float)
    return float(np.nanmean(net) / np.nanmean(stop)) if len(net) else np.nan


def summarize(trades: pd.DataFrame) -> dict:
    """Resumo de um conjunto de trades já líquidos (net_ret, stop_rel, ts)."""
    if trades.empty:
        return {"n": 0}
    mt = cluster_mean_test(trades["net_ret"].to_numpy(), day_clusters(trades["ts"]))
    return {
        "n": mt.n,
        "n_clusters": mt.n_clusters,
        "mean_bps": mt.mean * 1e4,
        "t": mt.t,
        "p_two": mt.p_two,
        "p_one_pos": mt.p_one_pos,
        "exp_R": expectancy_r(trades["net_ret"].to_numpy(), trades["stop_rel"].to_numpy()),
        "hit_rate": float((trades["net_ret"] > 0).mean()),
        "take_share": float((trades["exit_reason"] == "take").mean()),
        "stop_share": float((trades["exit_reason"] == "stop").mean()),
    }


def select_config(rows: list[dict]) -> dict:
    """Regra de seleção pré-registrada: maior t entre as configurações com n >=
    N_MIN_TRADES; se nenhuma atinge, a de maior t (resultado sai preliminar)."""
    usable = [r for r in rows if r.get("n", 0) >= cfg.N_MIN_TRADES and np.isfinite(r.get("t", np.nan))]
    pool = usable or [r for r in rows if np.isfinite(r.get("t", np.nan))]
    return max(pool, key=lambda r: r["t"]) if pool else {}


def verdict(dev: dict, oos: dict | None, wf_mean: float) -> tuple[str, list[str]]:
    """Veredicto pré-registrado (texto em src/backtest_config.py). `dev`/`oos` =
    summarize() da configuração escolhida no cenário primário; `oos=None` quando
    a validação NÃO foi aberta. Devolve (veredito, razões).

    "não validado" não exige abrir o OOS: a regra pré-registrada é "<= 0 no OOS
    OU <= 0 no desenvolvimento". Sem edge nem in-sample, abrir o out-of-sample só
    queimaria o único dado intocado sem chance de validar."""
    if not dev or dev.get("n", 0) == 0:
        return "não validado", ["sem trades para avaliar no desenvolvimento"]
    if dev["mean_bps"] <= 0:
        return "não validado", [
            f"expectativa líquida no desenvolvimento <= 0 ({dev['mean_bps']:.2f} bps) — sem edge in-sample"
        ]
    if oos is None:
        return "preliminar", ["validação (out-of-sample) ainda não aberta"]
    if oos.get("n", 0) == 0:
        return "não validado", ["sem trades no OOS"]
    if oos["mean_bps"] <= 0:
        return "não validado", [f"expectativa líquida no OOS <= 0 ({oos['mean_bps']:.2f} bps)"]

    checks = {
        "dev: significativo com Bonferroni": dev["p_two"] < cfg.ALPHA_BONFERRONI,
        "dev: amostra mínima": dev["n"] >= cfg.N_MIN_TRADES,
        "dev: efeito mínimo": dev["exp_R"] >= cfg.MIN_EFFECT_R,
        "OOS: significativo (unilateral)": oos["p_one_pos"] < cfg.OOS_ALPHA,
        "OOS: amostra mínima": oos["n"] >= cfg.N_MIN_TRADES,
        "OOS: efeito mínimo": oos["exp_R"] >= cfg.MIN_EFFECT_R,
        "walk-forward: média > 0": bool(np.isfinite(wf_mean) and wf_mean > 0),
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return "validado", ["todos os critérios cumulativos atendidos"]
    return "preliminar", [f"falhou: {k}" for k in failed]
