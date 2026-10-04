"""Cálculo do índice de força (Fase 2 — Seção 3.0/3.1 do estudo prévio).

Princípio (Seção 3.0): o retorno de um par isolado mistura força da base e
fraqueza da cotada — não dá para separar os dois olhando um par sozinho.
Decompõe-se usando TODOS os pares cruzados disponíveis envolvendo cada
moeda como equações simultâneas.

- **Método A** (v1, decidido): média aritmética simples dos retornos
  sinalizados dos 7 pares de cada moeda. Dá magnitude, não só ranking.
- **Método C** (checagem de robustez): mesmo retorno sinalizado de base,
  mas cada pair-comparação vira só +1 (moeda "ganhou" esse confronto) ou -1
  ("perdeu") — soma esse placar nos 7 confrontos e ranqueia pelo total.
  Por usar sinal em vez de magnitude, um único par com movimento gigante
  não domina o resultado como pode dominar a média do Método A — é
  exatamente a robustez a outlier que a Seção 3.1 pede dessa variante, e é
  o que permite A e C divergirem de verdade (ver teste
  `test_metodo_c_diverge_de_a_quando_a_e_dominado_por_outlier`).

Regra anti-lookahead (Seção 3.2): a força atribuída ao timestamp T só pode
usar preços conhecidos até o fechamento do candle T-1. Isto é garantido
aqui por construção (ver `compute_pair_return`), não por filtro a
posteriori — e `tests/test_force_index.py` verifica isso explicitamente.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.pairs import CURRENCY_PRECEDENCE, generate_pairs, split_pair
from src.windows import window_anchor


def compute_pair_return(close: pd.Series, variant: str) -> pd.Series:
    """Retorno acumulado do par desde a abertura da janela (`variant`),
    usando SÓ preços conhecidos antes do candle corrente.

    `close` deve ser uma Series de preços de fechamento indexada por
    timestamp UTC (DatetimeIndex), ordenada, de UM par.

    Anti-lookahead por construção: usamos `prev_close = close.shift(1)` (o
    fechamento do candle anterior, já conhecido no início do candle
    corrente) tanto como "preço atual" quanto para fixar o preço-base da
    janela (o primeiro prev_close de cada grupo). O retorno na linha T
    nunca depende de close[T] — só de close[:T-1]. Isso é verificado em
    teste (test_force_index.test_retorno_nao_usa_close_do_proprio_candle).
    """
    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("compute_pair_return espera um índice DatetimeIndex (UTC)")

    prev_close = close.shift(1)
    anchor = window_anchor(close.index, variant)
    baseline = prev_close.groupby(anchor).transform("first")
    return prev_close / baseline - 1.0


def _pair_signs() -> list[tuple[str, str, str]]:
    """(par, moeda_base, moeda_cotada) para os 28 pares canônicos, na ordem
    de src.pairs.generate_pairs()."""
    return [(p, *split_pair(p)) for p in generate_pairs()]


def compute_force_index(
    closes: dict[str, pd.Series],
    variant: str,
    currencies: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula força (Método A) e ranking (Método C) para cada moeda, em
    todos os timestamps onde há pelo menos um par disponível.

    `closes`: dict {par: Series de close indexada por ts UTC}, um par por
    par cruzado canônico (ex: {"EURUSD": serie, "EURGBP": serie, ...}).
    Não precisa ter os 28 — útil pra testar com um universo reduzido de
    moedas, desde que `currencies` seja passado coerente com os pares
    fornecidos.

    Retorna (force_a, rank_c): dois DataFrames indexados por timestamp,
    colunas = moedas. `force_a` é a média simples dos retornos sinalizados
    (NaN se nenhum par da moeda tiver dado naquele timestamp). `rank_c` é o
    ranking ordinal (1 = mais forte) do placar de vitórias/derrotas do
    Método C — ver docstring do módulo —, com empate resolvido pela média
    das posições (`Series.rank(method="average")`); NaN onde a moeda não
    tinha nenhum par disponível naquela linha.
    """
    currencies = currencies if currencies is not None else CURRENCY_PRECEDENCE
    pair_signs = [(p, b, q) for p, b, q in _pair_signs() if b in currencies and q in currencies]

    # Retorno de cada par, já no "sinal" de cada moeda que ele afeta.
    # contrib[moeda] = lista de Series (+retorno se moeda é base, -retorno se é cotada).
    contrib: dict[str, list[pd.Series]] = {c: [] for c in currencies}
    for pair, base, quote in pair_signs:
        if pair not in closes:
            continue
        ret = compute_pair_return(closes[pair], variant)
        contrib[base].append(ret)
        contrib[quote].append(-ret)

    force_cols = {}
    score_cols = {}
    for currency in currencies:
        series_list = contrib[currency]
        if not series_list:
            continue
        wide = pd.concat(series_list, axis=1)
        force_cols[currency] = wide.mean(axis=1, skipna=True)
        # min_count=1: linha com TODOS os pares NaN vira NaN no placar (não 0
        # "por convenção de soma vazia" do pandas) — "sem dado" não é "empate".
        score_cols[currency] = np.sign(wide).sum(axis=1, skipna=True, min_count=1)

    force_a = pd.DataFrame(force_cols).sort_index()
    score_c = pd.DataFrame(score_cols).sort_index()
    rank_c = score_c.rank(axis=1, ascending=False, method="average")
    return force_a, rank_c


def force_index_to_rows(
    force_a: pd.DataFrame, rank_c: pd.DataFrame, variant: str
) -> list[tuple]:
    """Achata (force_a, rank_c) em linhas (ts_utc, variant, currency,
    force_a, rank_c) prontas para src.db.insert_force_index. Pula células
    NaN (moeda sem par disponível naquele timestamp)."""
    rows: list[tuple] = []
    for currency in force_a.columns:
        fa = force_a[currency]
        rc = rank_c[currency]
        mask = fa.notna()
        # .as_unit("s") antes do astype: a resolução do DatetimeIndex não é
        # garantida (pandas >=2 preserva a resolução de origem — pode vir em
        # 's', 'us' ou 'ns' dependendo de como o índice foi construído), e
        # ".astype(int64) // 10**9" assumindo nanosegundos dá epoch errado
        # (visto rodando: colapsou timestamps de 2020-2026 todos pra "1").
        ts = fa.index[mask].as_unit("s").astype("int64").tolist()
        fa_vals = fa[mask].tolist()
        rc_vals = rc[mask].tolist()
        rows.extend(
            (t, variant, currency, float(a), float(c) if not np.isnan(c) else None)
            for t, a, c in zip(ts, fa_vals, rc_vals)
        )
    return rows
