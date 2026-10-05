#!/usr/bin/env python3
"""Fase 4b — estudo de eventos EXPLORATÓRIO, só período de desenvolvimento.

Pergunta: depois do sinal, o preço continua (momentum) ou reverte, e em qual
horizonte? Mede o retorno futuro NA DIREÇÃO do sinal, de 5 min a 24h, sem
stop/take (para isolar a previsibilidade do desenho de saída). É exploração:
serve para formar hipóteses, não para validar nada. Lê só eventos de
desenvolvimento (`load_events(..., 'dev')`); a validação continua intocada.

Contabilidade de múltiplos testes: 9 configurações × 8 horizontes = 72 células;
só se destaca como "forte" o que passa Bonferroni com m = 72. Mesmo assim,
qualquer coisa que apareça aqui é hipótese a pré-registrar e testar UMA vez no
out-of-sample — não um resultado.

Inclui uma checagem de calibração do próprio teste: inverter o sinal da
direção ao acaso (hipótese nula verdadeira por construção) tem que rejeitar
~5% das vezes; se rejeitar muito mais, o erro-padrão por cluster está subestimado
e nenhuma conclusão deste estudo vale.

Uso:
    python -m scripts.event_study_dev
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
from src.backtest_io import config_id, configs, load_events
from src.loaders import load_ohlc
from src.market_hours import in_rollover
from src.validation_stats import cluster_mean_test, day_clusters

HORIZONS = (1, 3, 6, 12, 36, 72, 144, 288)  # candles M5: 5min 15min 30min 1h 3h 6h 12h 24h
M_CELLS = len(cfg.VARIANTS) * len(cfg.K_MIN_GRID) * len(HORIZONS)
ALPHA_CELL = cfg.ALPHA / M_CELLS


def forward_signed_returns(df: pd.DataFrame, positions: np.ndarray, direction: np.ndarray) -> dict[int, np.ndarray]:
    """Retorno log de open[T] até o close do h-ésimo candle, com sinal da
    direção do trade. NaN se faltarem candles ou houver gap na janela."""
    ts = df.index.as_unit("s").astype("int64").to_numpy()
    n = len(ts)
    gap = np.concatenate([[0], np.diff(ts) > cfg.GAP_THRESHOLD_S]).astype(int)
    cg = np.cumsum(gap)
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    out = {}
    for h in HORIZONS:
        end = positions + h - 1
        ok = end < n
        e = np.minimum(end, n - 1)
        ok &= (cg[e] - cg[positions]) == 0
        out[h] = np.where(ok, direction * np.log(c[e] / o[positions]), np.nan)
    return out


def event_returns(events: pd.DataFrame, ohlc) -> pd.DataFrame:
    res = {h: np.full(len(events), np.nan) for h in HORIZONS}
    for pair, grp in events.groupby("pair"):
        df = ohlc[pair]
        pos = df.index.get_indexer(pd.DatetimeIndex(grp["ts"]))
        ok = pos >= 0
        if not ok.any():
            continue
        r = forward_signed_returns(df, pos[ok], grp["direction"].to_numpy()[ok].astype(float))
        rows = events.index.get_indexer(grp.index[ok])
        for h in HORIZONS:
            res[h][rows] = r[h]
    return pd.DataFrame({f"r{h}": v for h, v in res.items()}, index=events.index)


def null_calibration(r: np.ndarray, clusters: np.ndarray, draws: int = 300, seed: int = 0) -> float:
    """Taxa de rejeição a 5% do teste por cluster quando o sinal é sorteado ao acaso."""
    rng = np.random.default_rng(seed)
    keep = np.isfinite(r)
    r, cl = r[keep], clusters[keep]
    rej = 0
    for _ in range(draws):
        s = rng.choice([-1.0, 1.0], size=len(r))
        mt = cluster_mean_test(r * s, cl)
        rej += abs(mt.t) > 1.96 if np.isfinite(mt.t) else 0
    return rej / draws


def main() -> None:
    conn = db.connect(config.DB_PATH)
    print("Carregando OHLC...")
    ohlc = load_ohlc(conn)

    lines = ["# Fase 4b — estudo de eventos (exploratório, só desenvolvimento)\n"]
    lines.append(
        "Retorno futuro **na direção do sinal**, de open[T] até o fechamento do h-ésimo candle M5 "
        "(h = 1, 3, 6, 12, 36, 72, 144, 288 → 5 min a 24 h), em bps, **bruto** e **líquido de 1× spread** "
        "(custo de ida-e-volta do cenário otimista). Positivo = continuação; negativo = reversão. "
        "t robusto a cluster por dia. Eventos no rollover são excluídos. **Só desenvolvimento.**\n"
    )
    lines.append(
        f"Múltiplos testes: {M_CELLS} células por tabela → só se destaca (**negrito**) |t| que passa "
        f"Bonferroni, α = {cfg.ALPHA}/{M_CELLS} = {ALPHA_CELL:.5f}. Exploração gera hipóteses; não valida nada.\n"
    )

    gross_tbl, net_tbl = {}, {}
    sample_for_null = None
    for variant, k in configs():
        cid = config_id(variant, k)
        ev = load_events(conn, variant, k, "dev").reset_index(drop=True)
        ev = ev[~in_rollover(pd.DatetimeIndex(ev["ts"])) & np.isfinite(ev["spread_rel"])].reset_index(drop=True)
        rets = event_returns(ev, ohlc)
        cl = day_clusters(ev["ts"])
        for h in HORIZONS:
            r = rets[f"r{h}"].to_numpy()
            g = cluster_mean_test(r, cl)
            n_ = cluster_mean_test(r - ev["spread_rel"].to_numpy(), cl)
            gross_tbl[(cid, h)] = (g.n, g.mean * 1e4, g.t, g.p_two)
            net_tbl[(cid, h)] = (n_.n, n_.mean * 1e4, n_.t, n_.p_two)
        if cid == "session_k5":
            sample_for_null = (rets["r36"].to_numpy(), cl)
        print(f"  {cid}: {len(ev)} eventos")

    def render(title, tbl):
        lines.append(f"## {title}\n")
        lines.append("| config | n(h=36) | " + " | ".join(f"h={h}" for h in HORIZONS) + " |")
        lines.append("|---|---|" + "---|" * len(HORIZONS))
        for variant, k in configs():
            cid = config_id(variant, k)
            cells = []
            for h in HORIZONS:
                n, m, t, p = tbl[(cid, h)]
                txt = f"{m:+.1f} (t {t:+.1f})"
                cells.append(f"**{txt}**" if (np.isfinite(p) and p < ALPHA_CELL) else txt)
            lines.append(f"| {cid} | {tbl[(cid, 36)][0]} | " + " | ".join(cells) + " |")
        lines.append("")

    render("Retorno bruto na direção do sinal (bps, t)", gross_tbl)
    render("Retorno líquido de 1× spread (bps, t)", net_tbl)

    if sample_for_null is not None:
        rej = null_calibration(*sample_for_null)
        lines.append("## Calibração do teste (hipótese nula verdadeira por construção)\n")
        lines.append(
            f"Direção sorteada ao acaso em `session_k5`, h=36, 300 sorteios: rejeição a 5% = **{rej:.1%}** "
            "(esperado ≈ 5%). Se estivesse bem acima, o erro-padrão por cluster estaria subestimado.\n"
        )
        print(f"calibração do teste: rejeição a 5% = {rej:.1%}")

    Path("reports/fase4b_event_study_dev.md").write_text("\n".join(lines), encoding="utf-8")
    print("escrito reports/fase4b_event_study_dev.md")
    conn.close()


if __name__ == "__main__":
    main()
