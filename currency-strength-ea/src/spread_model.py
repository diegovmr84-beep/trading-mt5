"""Modelo de spread por par/sessão e filtro de pares operáveis (Fase 3, item 2).

Fonte: `spread_samples` da Fase 1 (amostragem ao vivo na Exness Trial,
2026-09-03 a 2026-10-04) — a ÚNICA fonte de spread real da corretora que
temos. O `broker_spread` dos candles Dukascopy é nível interbancário (mais
apertado que varejo) e não serve para isso.

## Correção (descoberta na análise de operabilidade, Fase 4)

A primeira versão desta tabela usava TODAS as amostras. Ao olhar spread por
hora do dia, apareceu que 33,5% das amostras foram gravadas com o mercado
FECHADO (sábado/domingo, cotação congelada) e que o spread explode no rollover
(17:00 de NY: EURNZD chega a ~28 pips, GBPJPY ~21). Isso inflava o quantil de
spread de forma arbitrária. Agora:

- a tabela usa só amostras com mercado ABERTO e FORA do rollover
  (src/market_hours.py, com horário de verão dos EUA);
- o rollover vira janela proibida: evento nesse horário nunca é operável.

## Achado que limita o que esta tabela pode dizer

Fora do rollover o spread medido de cada par é **constante** ao longo de todas
as horas — não varia entre Tóquio, Londres e NY, como uma conta real varia.
Isso indica spread fixo/simulado da conta Trial: esta tabela é um **piso** de
custo, não uma estimativa do spread real de execução. A Fase 4 trata isso
com cenários de custo (multiplicadores sobre este piso), não com a tabela como
verdade.

Outras limitações: o spread só foi amostrado em 2026 mas o backtest cobre
2020-2026; e essas amostras caem todas no período de VALIDAÇÃO do split 70/30
(spread não depende do resultado da estratégia, então não vaza edge, mas é uma
exceção registrada).

O filtro compara o spread RELATIVO ((ask-bid)/mid) com a distância do take
calibrada (também relativa):

    spread_rel(par, sessão)  <=  max_spread_to_take * take_rel   e   fora do rollover
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.market_hours import in_rollover, market_closed
from src.sessions import classify_session


@dataclass(frozen=True)
class SpreadParams:
    quantile: float = 0.75           # quantil do spread relativo por (par, sessão)
    max_spread_to_take: float = 0.25  # spread tolerado como fração da distância do take


def spread_table(conn, quantile: float) -> pd.Series:
    """Series indexada por (pair, session) com o quantil do spread relativo,
    calculado só com mercado aberto e fora do rollover."""
    df = pd.read_sql_query(
        "SELECT s.name AS pair, ss.session AS session, ss.ts_utc AS ts_utc, "
        "(ss.ask - ss.bid) / ((ss.ask + ss.bid) / 2.0) AS rel "
        "FROM spread_samples ss JOIN symbols s ON s.id = ss.symbol_id "
        "WHERE ss.ask > 0 AND ss.bid > 0",
        conn,
    )
    idx = pd.DatetimeIndex(pd.to_datetime(df["ts_utc"], unit="s", utc=True))
    keep = ~(market_closed(idx) | in_rollover(idx))
    return df[keep].groupby(["pair", "session"])["rel"].quantile(quantile)


def apply_spread_filter(
    events: pd.DataFrame, table: pd.Series, params: SpreadParams
) -> pd.DataFrame:
    """Acrescenta `session`, `rollover`, `spread_rel` e `spread_ok`. Par/sessão
    sem amostra de spread => spread_rel NaN => spread_ok False (conservador:
    sem dado de custo, não assume que o trade é viável)."""
    out = events.copy()
    ts = pd.DatetimeIndex(out["ts"])
    out["session"] = [classify_session(t.to_pydatetime()) for t in ts]
    out["rollover"] = in_rollover(ts)
    keys = list(zip(out["pair"], out["session"]))
    out["spread_rel"] = table.reindex(pd.MultiIndex.from_tuples(keys, names=["pair", "session"])).to_numpy()
    cost_ok = (out["spread_rel"] <= params.max_spread_to_take * out["take_rel"]).fillna(False)
    out["spread_ok"] = cost_ok & ~out["rollover"]
    return out
