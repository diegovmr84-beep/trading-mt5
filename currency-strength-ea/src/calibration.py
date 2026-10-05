"""Calibração de stop/take (Fase 3, item 4; Seção 5 do estudo).

Regra de integridade estatística (não é sugestão de estilo): a calibração usa
EXCLUSIVAMENTE eventos do período de desenvolvimento. `calibrate_stop_take`
recusa (levanta `ValidationLeakError`) qualquer evento em/depois do corte —
não confia em quem chama ter filtrado certo.

## O que é medido

Para cada evento de sinal (entrada na abertura do candle T), medimos nos
`horizon` candles seguintes o quanto o preço andou a favor (MFE, excursão
favorável máxima) e contra (MAE, excursão adversa máxima) a direção do
trade, em retorno log. Para ser comparável entre pares de volatilidades
diferentes, normalizamos por `sigma1 * sqrt(horizon)` — o desvio esperado de
um passeio aleatório nesse horizonte (sigma1 = volatilidade por candle do
par no momento do sinal, só passado). Unidade resultante: "z de horizonte".

Stop e take de cada nível de intensidade nascem dessa relação medida:

    take_z(bucket) = quantil `q_take` da distribuição de MFE_z do bucket
    stop_z(bucket) = quantil `q_stop` da distribuição de MAE_z do bucket

Intensidade do sinal = |z_pair| (movimento padronizado do par negociado),
dividida em `n_buckets` faixas por quantis dos eventos de DESENVOLVIMENTO; as
mesmas bordas são aplicadas depois, sem reajuste, aos eventos de validação.

`q_take`, `q_stop`, `horizon` e `n_buckets` são parâmetros varridos na Fase
4, não otimizados aqui. MFE/MAE medem trajetória após a entrada (olham o
futuro de propósito — é a variável-resposta da calibração), mas nada disso
alimenta a decisão de gerar o sinal, que só usa o passado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from src.split import ValidationLeakError


@dataclass(frozen=True)
class CalibrationParams:
    horizon: int = 36          # candles M5 (~3h) de exposição medida após a entrada
    q_take: float = 0.5        # quantil do MFE usado como take
    q_stop: float = 0.75       # quantil do MAE usado como stop
    n_buckets: int = 4         # faixas de intensidade |z_pair|
    max_span_factor: float = 2.0  # janela de `horizon` candles que dure > fator*horizon*5min é descartada (gap no meio)


def embargo_seconds(params: CalibrationParams) -> int:
    """Quanto antes do corte dev/validação um evento ainda "enxerga" o período
    de validação através da janela de resultado (MFE/MAE olham `horizon`
    candles à frente, até `max_span_factor` vezes a duração nominal). Eventos
    dentro desse intervalo ficam em embargo (purga): não entram na calibração
    (usariam preço de validação) nem contam como validação (o sinal nasceu
    antes do corte, mas o resultado se mistura com ele)."""
    return int(params.horizon * 300 * params.max_span_factor)


def forward_excursions(
    ohlc: pd.DataFrame,
    positions: np.ndarray,
    direction: np.ndarray,
    horizon: int,
    max_span_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """(mfe, mae) em retorno log, por evento. `ohlc`: DataFrame com colunas
    open/high/low indexado por DatetimeIndex ordenado; `positions`: posição
    inteira (linha) do candle de entrada de cada evento; `direction`: +1
    long / -1 short. Entrada = open do candle de entrada. NaN quando faltam
    `horizon` candles à frente ou há gap dentro da janela."""
    n = len(ohlc)
    ts_s = ohlc.index.as_unit("s").astype("int64").to_numpy()
    o = ohlc["open"].to_numpy()
    hi_arr = ohlc["high"].to_numpy()
    lo_arr = ohlc["low"].to_numpy()

    idx = positions[:, None] + np.arange(horizon)[None, :]
    ok = idx[:, -1] < n
    idx = np.minimum(idx, n - 1)
    ok &= (ts_s[idx[:, -1]] - ts_s[positions]) <= max_span_s

    entry = o[positions]
    hi = hi_arr[idx].max(axis=1)
    lo = lo_arr[idx].min(axis=1)
    up = np.log(hi / entry)
    down = np.log(entry / lo)
    mfe = np.where(direction > 0, up, down)
    mae = np.where(direction > 0, down, up)
    mfe = np.where(ok, mfe, np.nan)
    mae = np.where(ok, mae, np.nan)
    return mfe, mae


def add_excursions(
    events: pd.DataFrame,
    load_ohlc: Callable[[str], pd.DataFrame],
    params: CalibrationParams,
) -> pd.DataFrame:
    """Acrescenta `mfe_z` e `mae_z` (unidades de sigma1*sqrt(horizon)) a
    `events`. `load_ohlc(pair)` devolve o OHLC completo do par (cache fica a
    cargo de quem chama). Só para medir resultado de eventos — nunca entra na
    geração do sinal."""
    out = events.copy()
    out["mfe_z"] = np.nan
    out["mae_z"] = np.nan
    max_span_s = params.horizon * 300 * params.max_span_factor
    for pair, grp in out.groupby("pair"):
        ohlc = load_ohlc(pair)
        positions = ohlc.index.get_indexer(pd.DatetimeIndex(grp["ts"]))
        found = positions >= 0
        if not found.any():
            continue
        mfe, mae = forward_excursions(
            ohlc,
            positions[found],
            grp["direction"].to_numpy()[found],
            params.horizon,
            max_span_s,
        )
        scale = grp["sigma1"].to_numpy()[found] * np.sqrt(params.horizon)
        rows = grp.index[found]
        out.loc[rows, "mfe_z"] = mfe / scale
        out.loc[rows, "mae_z"] = mae / scale
    return out


def bucket_edges(intensity_dev: np.ndarray, n_buckets: int) -> np.ndarray:
    """Bordas por quantis da intensidade dos eventos de DESENVOLVIMENTO.
    Extremos abertos (-inf/+inf) para que eventos de validação fora da faixa
    observada na calibração caiam no primeiro/último bucket, sem reajuste."""
    edges = np.quantile(intensity_dev, np.linspace(0, 1, n_buckets + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    return edges


def assign_bucket(intensity: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(edges, intensity, side="right") - 1, 0, len(edges) - 2)


def calibrate_stop_take(
    events_dev: pd.DataFrame, cutoff_ts: int, params: CalibrationParams
) -> pd.DataFrame:
    """Tabela bucket -> (take_z, stop_z), calibrada só com `events_dev` (que
    precisa ter `ts`, `z_pair`, `mfe_z`, `mae_z`). Levanta ValidationLeakError
    se algum evento for do período de validação."""
    ts_epoch = pd.DatetimeIndex(events_dev["ts"]).as_unit("s").astype("int64").to_numpy()
    leak = ts_epoch + embargo_seconds(params) > cutoff_ts
    if leak.any():
        raise ValidationLeakError(
            f"{leak.sum()} evento(s) em/após o corte dev/validação — ou tão perto dele que a janela "
            "de resultado (MFE/MAE) invade a validação — entraram na calibração de stop/take. "
            "Isso invalida o out-of-sample."
        )
    usable = events_dev.dropna(subset=["mfe_z", "mae_z"])
    if len(usable) < params.n_buckets:
        raise ValueError(f"eventos insuficientes para calibrar ({len(usable)})")

    intensity = usable["z_pair"].abs().to_numpy()
    edges = bucket_edges(intensity, params.n_buckets)
    bucket = assign_bucket(intensity, edges)

    rows = []
    for b in range(params.n_buckets):
        sel = usable[bucket == b]
        rows.append(
            {
                "bucket": b,
                "z_lo": edges[b],
                "z_hi": edges[b + 1],
                "take_z": float(np.quantile(sel["mfe_z"], params.q_take)) if len(sel) else np.nan,
                "stop_z": float(np.quantile(sel["mae_z"], params.q_stop)) if len(sel) else np.nan,
                "n_events": int(len(sel)),
            }
        )
    return pd.DataFrame(rows)


def apply_calibration(events: pd.DataFrame, table: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Atribui bucket/take/stop a QUALQUER evento (dev ou validação) usando a
    tabela já calibrada — sem reajustar nada. `take_rel`/`stop_rel` em retorno
    log (distância de preço relativa), prontos para comparar com spread."""
    out = events.copy()
    edges = np.concatenate([table["z_lo"].to_numpy(), [table["z_hi"].to_numpy()[-1]]])
    bucket = assign_bucket(out["z_pair"].abs().to_numpy(), edges)
    out["bucket"] = bucket
    out["take_z"] = table["take_z"].to_numpy()[bucket]
    out["stop_z"] = table["stop_z"].to_numpy()[bucket]
    scale = out["sigma1"].to_numpy() * np.sqrt(horizon)
    out["take_rel"] = out["take_z"] * scale
    out["stop_rel"] = out["stop_z"] * scale
    return out
