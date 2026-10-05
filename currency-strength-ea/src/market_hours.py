"""Horário de mercado FX: fim de semana e rollover, com horário de verão dos EUA.

O mercado FX abre domingo 17:00 e fecha sexta 17:00 no horário de Nova York, e
o rollover diário (quando o spread das corretoras explode) é às 17:00 de NY.
Em UTC isso se desloca uma hora com o horário de verão dos EUA (21:00 UTC no
verão, 22:00 UTC no inverno) — por isso o cálculo é feito em hora LOCAL de NY,
senão metade do histórico (2020-2026 cobre vários invernos) teria a janela de
rollover uma hora fora do lugar.

Regra de horário de verão dos EUA (vigente desde 2007): começa no 2º domingo de
março às 02:00 locais (07:00 UTC), termina no 1º domingo de novembro às 02:00
locais (06:00 UTC). Implementada à mão (sem `zoneinfo`/`tzdata`) para não
depender de pacote de fuso que o Windows não traz por padrão.

Motivação (descoberta ao analisar os spreads da Fase 1): 33,5% das amostras de
spread foram gravadas com o mercado fechado (cotação congelada, spread largo) e
parte do resto caía no rollover — ambos contaminavam o spread "normal" por par.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROLLOVER_LOCAL_HOURS = (16, 17, 18)   # hora local de NY: 1h antes e 1h depois das 17:00


def _nth_sunday(year: int, month: int, n: int) -> int:
    """Dia do mês do n-ésimo domingo."""
    first_weekday = calendar.weekday(year, month, 1)  # 0=segunda
    first_sunday = 1 + (6 - first_weekday) % 7
    return first_sunday + 7 * (n - 1)


def us_dst(index: pd.DatetimeIndex) -> np.ndarray:
    """True onde os EUA estão em horário de verão (EDT, UTC-4)."""
    idx = index.tz_convert("UTC") if index.tz is not None else index.tz_localize("UTC")
    secs = idx.as_unit("s").astype("int64").to_numpy()
    out = np.zeros(len(idx), dtype=bool)
    for year in np.unique(idx.year):
        start = int(datetime(year, 3, _nth_sunday(year, 3, 2), 7, tzinfo=timezone.utc).timestamp())
        end = int(datetime(year, 11, _nth_sunday(year, 11, 1), 6, tzinfo=timezone.utc).timestamp())
        in_year = idx.year == year
        out |= in_year & (secs >= start) & (secs < end)
    return out


def ny_local(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Mesmos instantes em hora local de NY (tz-naive, só para extrair hora/dia)."""
    idx = index.tz_convert("UTC") if index.tz is not None else index.tz_localize("UTC")
    offset_h = np.where(us_dst(idx), -4, -5)
    return (idx.tz_localize(None) + pd.to_timedelta(offset_h, unit="h"))


def in_rollover(index: pd.DatetimeIndex) -> np.ndarray:
    """True nas horas ao redor do rollover (16:00-18:59 locais de NY)."""
    return np.isin(ny_local(index).hour, ROLLOVER_LOCAL_HOURS)


def market_closed(index: pd.DatetimeIndex) -> np.ndarray:
    """True com o mercado fechado: de sexta 17:00 a domingo 17:00 (hora de NY)."""
    local = ny_local(index)
    dow, hour = local.dayofweek, local.hour
    return (dow == 5) | ((dow == 4) & (hour >= 17)) | ((dow == 6) & (hour < 17))
