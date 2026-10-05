"""Modelo de spread por par/sessão e filtro de pares operáveis (Fase 3, item 2).

Fonte: `spread_samples` da Fase 1 (amostragem ao vivo na Exness Trial,
2026-09-03 a 2026-10-04) — a ÚNICA fonte de spread real da corretora que
temos. O `broker_spread` dos candles Dukascopy é nível interbancário (mais
apertado que varejo) e não serve para isso.

Limitação assumida e documentada: o spread só foi amostrado em 2026, mas o
backtest cobre 2020-2026. Aplicamos a tabela (par, sessão) a todo o histórico
— o spread varia de fato entre regimes de mercado, então isto subestima o
custo em períodos de stress e é uma aproximação, não uma medida. Por isso a
Fase 4 roda 3 cenários de custo (otimista/realista/pessimista) em vez de um.
Nota de integridade: o spread de 2026 cai todo no período de VALIDAÇÃO do
split 70/30. Spread não é informação de resultado da estratégia (não depende
de retorno), então não vaza edge — mas é uma exceção ao "validação nunca é
vista" e fica registrada aqui por transparência.

O filtro compara o spread RELATIVO ((ask-bid)/mid) com a distância do take
calibrada (também relativa): um candidato só vira trade se

    spread_rel(par, sessão)  <=  max_spread_to_take * take_rel

— "a operação não nasce negativa demais", que é o que a Seção 5 pede (NZD/JPY
com spread alto o bastante para inviabilizar o trade).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.sessions import classify_session


@dataclass(frozen=True)
class SpreadParams:
    quantile: float = 0.75           # quantil do spread relativo por (par, sessão): 0.5 otimista .. 0.95 pessimista
    max_spread_to_take: float = 0.25  # spread tolerado como fração da distância do take


def spread_table(conn, quantile: float) -> pd.Series:
    """Series indexada por (pair, session) com o quantil do spread relativo."""
    df = pd.read_sql_query(
        "SELECT s.name AS pair, ss.session AS session, "
        "(ss.ask - ss.bid) / ((ss.ask + ss.bid) / 2.0) AS rel "
        "FROM spread_samples ss JOIN symbols s ON s.id = ss.symbol_id "
        "WHERE ss.ask > 0 AND ss.bid > 0",
        conn,
    )
    return df.groupby(["pair", "session"])["rel"].quantile(quantile)


def apply_spread_filter(
    events: pd.DataFrame, table: pd.Series, params: SpreadParams
) -> pd.DataFrame:
    """Acrescenta `session`, `spread_rel` e `spread_ok`. Par/sessão sem amostra
    de spread => spread_rel NaN => spread_ok False (conservador: sem dado de
    custo, não assume que o trade é viável)."""
    out = events.copy()
    ts = pd.DatetimeIndex(out["ts"])
    out["session"] = [classify_session(t.to_pydatetime()) for t in ts]
    keys = list(zip(out["pair"], out["session"]))
    out["spread_rel"] = table.reindex(pd.MultiIndex.from_tuples(keys, names=["pair", "session"])).to_numpy()
    out["spread_ok"] = (out["spread_rel"] <= params.max_spread_to_take * out["take_rel"]).fillna(False)
    return out
