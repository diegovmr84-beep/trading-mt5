"""Decodificação do formato de tick histórico da Dukascopy (.bi5).

Fonte usada e não fabricada aqui: Dukascopy expõe um feed público de tick
history em `https://datafeed.dukascopy.com/datafeed/`, um arquivo por hora
UTC por símbolo. O formato foi confirmado por múltiplas implementações
open-source independentes (não é documentação oficial da Dukascopy, mas o
formato é consistente entre elas):

    URL:   https://datafeed.dukascopy.com/datafeed/{PAIR}/{YYYY}/{MM 0-idx}/{DD}/{HH}h_ticks.bi5
    Corpo: stream LZMA de registros de 20 bytes, big-endian, cada um:
               int32   ms_offset    milissegundos desde o início da hora
               int32   ask_raw      preço de venda (inteiro bruto)
               int32   bid_raw      preço de compra (inteiro bruto)
               float32 ask_volume
               float32 bid_volume
           preço real = raw / POINT_DIVISOR (100000 padrão, 1000 para JPY)
    Hora sem nenhum tick (fim de semana, feriado): arquivo de 0 bytes — não
    é erro.

IMPORTANTE — isto não foi validado contra um arquivo real: o ambiente onde
este código foi escrito não tem acesso de rede à Dukascopy (só a um
allowlist de hosts). `scripts/dukascopy_smoke_test.py` baixa UM arquivo de
UMA hora e imprime o resultado decodificado — rode-o e confira visualmente
antes de disparar o backfill completo de vários anos.
"""

from __future__ import annotations

import lzma
import struct
from dataclasses import dataclass
from datetime import datetime, timezone

_RECORD_FORMAT = ">3i2f"
_RECORD_SIZE = struct.calcsize(_RECORD_FORMAT)

# O datafeed da Dukascopy responde 429 (Too Many Requests) já na primeira
# chamada quando o User-Agent é o padrão do `requests` (`python-requests/x`);
# com um User-Agent de navegador responde 200 normalmente. Descoberto rodando
# (não presumido): default -> 429, browser UA -> 200. Usado pelos dois scripts
# que baixam da Dukascopy (dukascopy_smoke_test.py e download_history_dukascopy.py).
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def point_divisor(pair: str) -> int:
    return 1000 if "JPY" in pair else 100000


@dataclass(frozen=True)
class Tick:
    ms_offset: int
    ask: float
    bid: float
    ask_volume: float
    bid_volume: float

    @property
    def mid(self) -> float:
        return (self.ask + self.bid) / 2.0


def bi5_url(pair: str, dt_hour_utc: datetime) -> str:
    """dt_hour_utc: qualquer datetime UTC dentro da hora desejada (só
    ano/mês/dia/hora são usados)."""
    return (
        f"https://datafeed.dukascopy.com/datafeed/{pair}/"
        f"{dt_hour_utc.year:04d}/{dt_hour_utc.month - 1:02d}/"
        f"{dt_hour_utc.day:02d}/{dt_hour_utc.hour:02d}h_ticks.bi5"
    )


def decode_bi5(raw_bytes: bytes, pair: str) -> list[Tick]:
    """Decodifica o conteúdo (já baixado) de um arquivo .bi5 em ticks.
    Corpo vazio é uma hora sem nenhum tick — retorna lista vazia, não é
    erro."""
    if not raw_bytes:
        return []

    decompressed = lzma.decompress(raw_bytes)
    divisor = point_divisor(pair)

    ticks = []
    for offset in range(0, len(decompressed) - _RECORD_SIZE + 1, _RECORD_SIZE):
        chunk = decompressed[offset : offset + _RECORD_SIZE]
        ms_offset, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(_RECORD_FORMAT, chunk)
        ticks.append(Tick(ms_offset, ask_raw / divisor, bid_raw / divisor, ask_vol, bid_vol))
    return ticks


def ticks_to_m5_candles(pair: str, hour_start_epoch: int, ticks: list[Tick]) -> list[tuple]:
    """Agrupa ticks de UMA hora (timestamps relativos ao início da hora) em
    candles M5, usando o preço médio (mid = (ask+bid)/2) como série de
    preço. Mid, não bid, propositalmente: a Seção 3.3 do estudo separa o
    cálculo do índice de força (que usa esta série) do filtro de spread
    (Fase 3) — usar mid evita embutir metade do spread na série de retorno
    usada pra decompor força, o que duplicaria o efeito do spread (uma vez
    aqui, de novo no filtro da Fase 3).

    Retorna linhas no formato esperado por db.insert_candles:
    (ts_utc, open, high, low, close, tick_volume, real_volume, broker_spread)
    — broker_spread aqui é o spread médio do bucket em pontos, guardado só
    como referência secundária (mesmo aviso de src/db.py: não é a fonte do
    levantamento de spread da Fase 1, que vem do spread_sampler ao vivo)."""
    divisor = point_divisor(pair)
    buckets: dict[int, list[Tick]] = {}
    for tick in sorted(ticks, key=lambda t: t.ms_offset):
        ts = hour_start_epoch + tick.ms_offset // 1000
        bucket_start = ts - (ts % 300)
        buckets.setdefault(bucket_start, []).append(tick)

    rows = []
    for bucket_start in sorted(buckets):
        bucket_ticks = buckets[bucket_start]
        mids = [t.mid for t in bucket_ticks]
        avg_spread_price = sum(t.ask - t.bid for t in bucket_ticks) / len(bucket_ticks)
        rows.append(
            (
                bucket_start,
                mids[0],
                max(mids),
                min(mids),
                mids[-1],
                len(bucket_ticks),
                0,
                round(avg_spread_price * divisor),
            )
        )
    return rows


def hour_start_epoch(dt_hour_utc: datetime) -> int:
    truncated = dt_hour_utc.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return int(truncated.timestamp())
