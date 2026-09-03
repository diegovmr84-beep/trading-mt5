"""Classificação de sessão de mercado por horário UTC.

IMPORTANTE — estas janelas são aproximações padrão de mercado, usadas aqui
apenas para SEGMENTAR o levantamento descritivo de spread da Fase 1 (Seção 6
do estudo: "spread médio/máximo... segmentado por sessão"). Elas NÃO são a
definição final da "janela de sessão" usada no índice de força — essa
definição é decidida empiricamente no backtest (Fase 4), testando as 3
variantes candidatas descritas na Seção 3.2 do estudo. Não confundir os dois
usos.

Janelas aproximadas (ignoram mudança de horário de verão nos países de
origem — é uma simplificação aceitável para fins descritivos; se isso vier
a importar para a decisão de negociação, será tratado com precisão na
Fase 4):

    Tóquio:            00:00 - 09:00 UTC
    Londres:           08:00 - 17:00 UTC
    Nova York:         13:00 - 22:00 UTC
    Overlap Londres/NY: 13:00 - 17:00 UTC (subconjunto de Londres e NY)
"""

from __future__ import annotations

from datetime import datetime, timezone

SESSION_WINDOWS_UTC: dict[str, tuple[int, int]] = {
    "tokyo": (0, 9),
    "london": (8, 17),
    "ny": (13, 22),
    "london_ny_overlap": (13, 17),
}


def classify_session(dt_utc: datetime) -> str:
    """Classifica um timestamp UTC numa sessão. Overlap tem prioridade sobre
    Londres/NY isolados quando o horário cai nos dois. Fora de todas as
    janelas conhecidas, retorna 'other' (ex: madrugada de baixa liquidez
    entre o fechamento de NY e a abertura de Tóquio)."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    hour = dt_utc.astimezone(timezone.utc).hour

    lo, hi = SESSION_WINDOWS_UTC["london_ny_overlap"]
    if lo <= hour < hi:
        return "london_ny_overlap"

    for name in ("tokyo", "london", "ny"):
        lo, hi = SESSION_WINDOWS_UTC[name]
        if lo <= hour < hi:
            return name

    return "other"
