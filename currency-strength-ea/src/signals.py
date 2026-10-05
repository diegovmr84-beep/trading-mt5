"""Geração de sinais candidatos (Fase 3, Seção 5 do estudo prévio).

Transforma o histórico de preços em **eventos de sinal** (onsets): momentos em
que uma moeda forte e uma moeda fraca da cesta formam um par candidato a
trade. Nada aqui calcula P&L (isso é Fase 4) nem olha resultado futuro — todo
o módulo usa só informação conhecida até o fechamento do candle T-1.

## "Significativo" — definição do teste (exigência explícita da Fase 3)

Para cada par (X base / Y cotada) e cada timestamp T, a comparação X vs Y é
"significativa a favor de X" quando

    z(T) = r(T) / ( sigma1(T) * sqrt(n(T)) )  >  z_crit

- r(T): retorno LOGARÍTMICO acumulado do par desde a abertura da janela
  corrente (mesma janela das variantes da Fase 2, src/windows.py), usando só
  fechamentos até T-1. Log, e não retorno simples, para a antissimetria ser
  exata (z de Y vs X = -z de X vs Y).
- sigma1(T): desvio-padrão dos retornos log por candle do próprio par nas
  últimas `VOL_LOOKBACK` observações (~10 dias úteis de M5), também só até T-1.
- n(T): nº de passos (candles) entre o preço-base da janela e o preço
  atual — sigma1*sqrt(n) é o desvio esperado de um passeio aleatório nessa
  distância.

z é, portanto, "o movimento acumulado do par, em unidades do que seria
esperado por acaso dado a volatilidade recente dele". NÃO é um p-value
válido (retornos têm cauda gorda e volatilidade que agrupa) — é uma régua
padronizada, comparável entre pares de volatilidades diferentes e entre
momentos diferentes da janela. A inferência estatística de verdade (Bonferroni,
out-of-sample, walk-forward) acontece no nível da ESTRATÉGIA, na Fase 4;
`z_crit` e `k_min` são parâmetros varridos lá, e cada comparação par-a-par
conta na contagem de testes do Bonferroni (até 7 por moeda candidata).

## Gaps (fim de semana, feriado)

Um intervalo > `GAP_THRESHOLD_S` entre candles consecutivos de um par encerra o
segmento de acumulação: retornos que atravessam o gap não entram nem na
estimativa de sigma1 nem em r(T), e o acúmulo recomeça no primeiro candle
depois do gap (tratando feriado como fim de semana, conforme a revisão da
Fase 1). Sem isso, o "retorno desde a abertura da janela" de uma segunda-feira
de manhã incluiria o gap de fim de semana inteiro e geraria sinais falsos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.pairs import CURRENCY_PRECEDENCE, split_pair
from src.windows import window_anchor

VOL_LOOKBACK = 2880        # candles M5 (~10 dias úteis) para estimar sigma1
VOL_MIN_PERIODS = 1000     # sem histórico suficiente, sigma1 = NaN e z = NaN
GAP_THRESHOLD_S = 7200     # gap > 2h encerra o segmento de acumulação


@dataclass(frozen=True)
class SignalParams:
    """Parâmetros do critério de entrada — todos varridos na Fase 4, nenhum
    otimizado aqui. Defaults são pontos de partida neutros, não resultado de
    ajuste."""

    k_min: int = 5                       # nº mínimo de moedas "vencidas" (de 7): 5, 6 ou 7
    z_crit: float = 2.0                  # limiar de z para chamar uma comparação de significativa
    require_pair_significance: bool = True  # o próprio par (forte vs fraca) também precisa de z>z_crit


def pair_zscore(
    close: pd.Series,
    variant: str,
    vol_lookback: int = VOL_LOOKBACK,
    vol_min_periods: int = VOL_MIN_PERIODS,
    gap_threshold_s: int = GAP_THRESHOLD_S,
) -> tuple[pd.Series, pd.Series]:
    """(z, sigma1) de UM par, indexados como `close` (DatetimeIndex UTC).

    Anti-lookahead por construção: o valor na linha T só depende de
    close[:T-1] (verificado em tests/test_signals.py)."""
    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("pair_zscore espera um índice DatetimeIndex (UTC)")

    ts = close.index
    lc = np.log(close)
    step_s = ts.to_series().diff().dt.total_seconds()
    gap = (step_s > gap_threshold_s).astype(np.int8)  # NaN (1ª linha) -> False

    # sigma1: std dos retornos por candle, excluindo os que atravessam gap;
    # shift(1) -> o valor em T só vê retornos até o candle T-1.
    lr = lc.diff().where(gap == 0)
    sigma1 = lr.rolling(vol_lookback, min_periods=vol_min_periods).std().shift(1)

    prev_lc = lc.shift(1)  # preço "atual" conhecido no início do candle T
    anchor = window_anchor(ts, variant).as_unit("s").astype("int64").to_numpy()
    gap_cum = gap.groupby(anchor).cumsum().to_numpy()
    keys = [anchor, gap_cum]  # segmento = janela + nº de gaps já ocorridos nela

    seg_started_after_gap = gap.groupby(keys).transform("first").to_numpy()  # 0 ou 1
    pos = prev_lc.groupby(keys).cumcount().to_numpy()
    # Segmento normal: preço-base = prev_close da 1ª linha (mercado contínuo).
    # Segmento pós-gap: prev_close da 1ª linha é o fechamento PRÉ-gap, então a
    # base passa a ser o fechamento do 1º candle pós-gap (prev_close da 2ª linha).
    is_base_row = pos == seg_started_after_gap
    baseline = prev_lc.where(is_base_row).groupby(keys).transform("first")
    n = pos - seg_started_after_gap

    r_acc = prev_lc - baseline
    valid = (n >= 1) & sigma1.notna().to_numpy() & (sigma1.to_numpy() > 0) & baseline.notna().to_numpy()
    z = (r_acc / (sigma1 * np.sqrt(np.maximum(n, 1)))).where(valid)
    return z, sigma1


def pair_zscores(
    closes: dict[str, pd.Series], variant: str, **kwargs
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(z_wide, sigma_wide): DataFrames ts x par, no índice-união dos pares."""
    z_cols, s_cols = {}, {}
    for pair, close in closes.items():
        z_cols[pair], s_cols[pair] = pair_zscore(close, variant, **kwargs)
    return pd.DataFrame(z_cols).sort_index(), pd.DataFrame(s_cols).sort_index()


def dominance_counts(
    z_wide: pd.DataFrame, z_crit: float, currencies: list[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Para cada moeda e timestamp: em quantos confrontos ela é significativamente
    mais forte (`strong`) / mais fraca (`weak`) que a outra moeda do par.
    Comparação com NaN conta como "não significativa" (False)."""
    currencies = currencies if currencies is not None else CURRENCY_PRECEDENCE
    n = len(z_wide)
    strong = {c: np.zeros(n, dtype=np.int8) for c in currencies}
    weak = {c: np.zeros(n, dtype=np.int8) for c in currencies}
    for pair in z_wide.columns:
        base, quote = split_pair(pair)
        if base not in strong or quote not in strong:
            continue
        z = z_wide[pair].to_numpy()
        base_wins = z > z_crit
        quote_wins = z < -z_crit
        strong[base] += base_wins
        weak[quote] += base_wins
        strong[quote] += quote_wins
        weak[base] += quote_wins
    return (
        pd.DataFrame(strong, index=z_wide.index),
        pd.DataFrame(weak, index=z_wide.index),
    )


def candidate_events(
    z_wide: pd.DataFrame,
    sigma_wide: pd.DataFrame,
    force_a: pd.DataFrame,
    rank_c: pd.DataFrame,
    params: SignalParams,
    currencies: list[str] | None = None,
) -> pd.DataFrame:
    """Eventos de ONSET de sinal: instantes em que um par passa de "sem sinal"
    para "sinal ativo" (ou muda de direção). Um sinal que persiste por 50
    candles gera 1 evento, não 50 — evita contar a mesma oportunidade várias
    vezes.

    Um par (base b, cotada q) tem sinal LONG quando b é forte (vence >= k_min
    das outras), q é fraca (perde para >= k_min), e — se
    `require_pair_significance` — o próprio par tem z > z_crit. SHORT é o
    espelho (q forte, b fraca, z < -z_crit).

    `priority`: posição do candidato entre os simultâneos naquele timestamp,
    ordenado pela diferença de força (Método A) forte - fraca, decrescente
    (1 = mais forte vs mais fraca) — é a lista ordenada que a Seção 5 manda
    percorrer, aplicando o filtro de spread de cima para baixo.
    """
    currencies = currencies if currencies is not None else CURRENCY_PRECEDENCE
    idx = z_wide.index
    strong_count, weak_count = dominance_counts(z_wide, params.z_crit, currencies)
    strong_flag = strong_count >= params.k_min
    weak_flag = weak_count >= params.k_min

    cidx = {c: i for i, c in enumerate(currencies)}
    sc_arr = strong_count[currencies].to_numpy()
    wc_arr = weak_count[currencies].to_numpy()
    fa_arr = force_a.reindex(idx).reindex(columns=currencies).to_numpy()
    rc_arr = rank_c.reindex(idx).reindex(columns=currencies).to_numpy()

    frames = []
    for pair in z_wide.columns:
        base, quote = split_pair(pair)
        if base not in cidx or quote not in cidx:
            continue
        z = z_wide[pair]
        if params.require_pair_significance:
            long_ = strong_flag[base] & weak_flag[quote] & (z > params.z_crit)
            short = strong_flag[quote] & weak_flag[base] & (z < -params.z_crit)
        else:
            long_ = strong_flag[base] & weak_flag[quote]
            short = strong_flag[quote] & weak_flag[base]
        direction = long_.astype(np.int8) - short.astype(np.int8)
        onset = (direction != 0) & (direction != direction.shift(1, fill_value=0))
        pos = np.flatnonzero(onset.to_numpy())
        if pos.size == 0:
            continue

        d = direction.to_numpy()[pos]
        s_i = np.where(d > 0, cidx[base], cidx[quote])
        w_i = np.where(d > 0, cidx[quote], cidx[base])
        inv = {i: c for c, i in cidx.items()}
        frames.append(
            pd.DataFrame(
                {
                    "ts": idx[pos],
                    "pair": pair,
                    "direction": d,
                    "strong_ccy": [inv[i] for i in s_i],
                    "weak_ccy": [inv[i] for i in w_i],
                    "n_strong": sc_arr[pos, s_i],
                    "n_weak": wc_arr[pos, w_i],
                    "z_pair": z.to_numpy()[pos],
                    "force_gap": fa_arr[pos, s_i] - fa_arr[pos, w_i],
                    "rank_c_strong": rc_arr[pos, s_i],
                    "rank_c_weak": rc_arr[pos, w_i],
                    "sigma1": sigma_wide[pair].to_numpy()[pos],
                }
            )
        )

    columns = [
        "ts", "pair", "direction", "strong_ccy", "weak_ccy", "n_strong", "n_weak",
        "z_pair", "force_gap", "rank_c_strong", "rank_c_weak", "sigma1", "priority",
    ]
    if not frames:
        return pd.DataFrame(columns=columns)
    events = pd.concat(frames, ignore_index=True).sort_values(["ts", "pair"], kind="stable")
    events["priority"] = (
        events.groupby("ts")["force_gap"].rank(ascending=False, method="first").astype(int)
    )
    return events.reset_index(drop=True)[columns]
