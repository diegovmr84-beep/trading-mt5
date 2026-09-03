import lzma
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dukascopy import (
    Tick,
    bi5_url,
    decode_bi5,
    hour_start_epoch,
    point_divisor,
    ticks_to_m5_candles,
)


def test_point_divisor():
    assert point_divisor("EURUSD") == 100000
    assert point_divisor("USDJPY") == 1000
    assert point_divisor("GBPJPY") == 1000
    assert point_divisor("AUDNZD") == 100000


def test_bi5_url_format_month_is_zero_indexed():
    dt = datetime(2024, 1, 15, 10, tzinfo=timezone.utc)
    url = bi5_url("EURUSD", dt)
    assert url == "https://datafeed.dukascopy.com/datafeed/EURUSD/2024/00/15/10h_ticks.bi5"


def test_decode_bi5_empty_body_is_empty_list():
    assert decode_bi5(b"", "EURUSD") == []


def test_decode_bi5_round_trip():
    """Round-trip usando o lzma padrão do Python (não é o arquivo real da
    Dukascopy, que não temos como baixar deste ambiente) — valida a lógica
    de struct/offset do decoder, não a compatibilidade exata do container
    LZMA da Dukascopy. Ver aviso em src/dukascopy.py."""
    records = [
        (0, 110500, 110480, 1.5, 2.0),
        (1500, 110510, 110490, 1.0, 1.0),
        (300_000, 110490, 110470, 3.0, 0.5),
    ]
    raw = b"".join(struct.pack(">3i2f", *r) for r in records)
    compressed = lzma.compress(raw)

    ticks = decode_bi5(compressed, "EURUSD")

    assert len(ticks) == 3
    assert ticks[0] == Tick(0, 1.105, 1.1048, 1.5, 2.0)
    assert ticks[2].ms_offset == 300_000


def test_ticks_to_m5_candles_buckets_correctly():
    ticks = [
        Tick(ms_offset=0, ask=1.1050, bid=1.1048, ask_volume=1, bid_volume=1),
        Tick(ms_offset=60_000, ask=1.1060, bid=1.1058, ask_volume=1, bid_volume=1),
        Tick(ms_offset=299_000, ask=1.1040, bid=1.1038, ask_volume=1, bid_volume=1),
        # segundo bucket M5 (>= 300s)
        Tick(ms_offset=300_500, ask=1.1070, bid=1.1068, ask_volume=1, bid_volume=1),
    ]
    hour_epoch = 1_700_000_000 - (1_700_000_000 % 3600)  # início de hora "redondo"

    rows = ticks_to_m5_candles("EURUSD", hour_epoch, ticks)

    assert len(rows) == 2
    first = rows[0]
    ts0, open_, high, low, close, n_ticks, real_vol, spread_points = first
    assert n_ticks == 3
    assert open_ == pytest.approx(1.1049)  # mid do primeiro tick
    assert close == pytest.approx(1.1039)  # mid do último tick do bucket
    assert high == pytest.approx(1.1059)
    assert low == pytest.approx(1.1039)
    assert real_vol == 0

    second = rows[1]
    assert second[5] == 1  # 1 tick só no segundo bucket


def test_hour_start_epoch_truncates_to_hour():
    dt = datetime(2024, 1, 15, 10, 37, 22, tzinfo=timezone.utc)
    epoch = hour_start_epoch(dt)
    expected = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    assert epoch == expected
