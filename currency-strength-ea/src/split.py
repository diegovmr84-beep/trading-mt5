"""Split desenvolvimento / validação (Seção 4.1 do estudo, 70% / 30%).

O período de validação (out-of-sample) nunca pode influenciar nenhum
parâmetro. Aqui só se define ONDE é o corte — uma única vez, na linha do
tempo calendário do histórico, e todo o resto do código importa daqui em vez
de recalcular (um corte recalculado em dois lugares acaba divergindo).
"""

from __future__ import annotations

DEV_FRACTION = 0.7


def dev_cutoff(ts_min: int, ts_max: int, fraction: float = DEV_FRACTION) -> int:
    """Epoch (segundos UTC) do corte: eventos com ts < corte são
    desenvolvimento; ts >= corte são validação."""
    if ts_max <= ts_min:
        raise ValueError("histórico vazio ou de um instante só — não há como dividir")
    return int(ts_min + fraction * (ts_max - ts_min))


class ValidationLeakError(ValueError):
    """Levantado quando algo tenta usar dado do período de validação numa
    etapa que só pode ver o período de desenvolvimento (calibração)."""
