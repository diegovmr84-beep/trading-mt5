"""Variantes da janela de cálculo do retorno usada no índice de força
(Fase 2, Seção 3.2 do estudo: "a definição exata é determinada
empiricamente pelo backtest" — aqui só garantimos que as três candidatas
existem como parâmetro, sem escolher nenhuma).

As três janelas resetam o "retorno acumulado" em horários diferentes do
dia UTC; fora isso o cálculo de retorno (src/force_index.py) é idêntico:

    daily    — reseta às 00:00 UTC (dia corrido)
    session  — reseta às 00:00 / 08:00 / 13:00 UTC (aberturas de
               Tóquio/Londres/NY — mesmos limiares de src/sessions.py)
    overlap  — reseta às 13:00 UTC (abertura do overlap Londres/NY, o
               período de maior liquidez)

Nenhuma das três é "a" janela do índice — a escolha é feita na Fase 4
comparando as três no período de desenvolvimento (70%). Aqui o código só
precisa suportar as três sem retrabalho.
"""

from __future__ import annotations

import pandas as pd

WINDOW_VARIANTS: tuple[str, ...] = ("daily", "session", "overlap")

# Limiares em horas UTC usados pela variante "session" — mesmos horários de
# abertura de sessão que src/sessions.py usa para classificar (Tóquio 00:00,
# Londres 08:00, NY 13:00). Não reimporta de lá porque sessions.py classifica
# um horário numa categoria (ex: "london_ny_overlap"); aqui só precisamos do
# horário de reset mais recente, que é outra pergunta.
_SESSION_RESET_HOURS = (0, 8, 13)
_OVERLAP_RESET_HOUR = 13


def window_anchor(index: pd.DatetimeIndex, variant: str) -> pd.DatetimeIndex:
    """Para cada timestamp (UTC) em `index`, devolve o início (timestamp) da
    janela de retorno à qual ele pertence, segundo `variant`. Timestamps com
    o mesmo anchor pertencem à mesma janela — agrupe por este valor para
    calcular o retorno acumulado dentro da janela (ver
    force_index.compute_pair_return)."""
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("window_anchor espera um pandas.DatetimeIndex (UTC)")

    day_start = index.normalize()  # floor para 00:00 UTC do mesmo dia

    if variant == "daily":
        return day_start

    if variant == "overlap":
        anchor = day_start + pd.Timedelta(hours=_OVERLAP_RESET_HOUR)
        # Antes das 13:00 UTC, a janela corrente começou às 13:00 do dia anterior.
        return anchor.where(index >= anchor, anchor - pd.Timedelta(days=1))

    if variant == "session":
        hours = index.hour
        # limiares (0, 8, 13): bucket = o maior limiar <= hora corrente.
        # Como 0 é sempre limiar, nunca precisa olhar o dia anterior.
        bucket_hour = pd.cut(
            hours,
            bins=[-1, _SESSION_RESET_HOURS[1] - 1, _SESSION_RESET_HOURS[2] - 1, 23],
            labels=list(_SESSION_RESET_HOURS),
        ).astype(int)
        return day_start + pd.to_timedelta(bucket_hour, unit="h")

    raise ValueError(f"variante de janela desconhecida: {variant!r} (válidas: {WINDOW_VARIANTS})")
