import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pairs import CURRENCY_PRECEDENCE, generate_pairs, split_pair, with_broker_suffix


def test_generates_28_pairs():
    pairs = generate_pairs()
    assert len(pairs) == 28
    assert len(set(pairs)) == 28


def test_each_currency_appears_seven_times():
    pairs = generate_pairs()
    counts = {c: 0 for c in CURRENCY_PRECEDENCE}
    for p in pairs:
        base, quote = split_pair(p)
        counts[base] += 1
        counts[quote] += 1
    assert all(n == 7 for n in counts.values())


def test_base_quote_follows_precedence_order():
    pairs = generate_pairs()
    for p in pairs:
        base, quote = split_pair(p)
        assert CURRENCY_PRECEDENCE.index(base) < CURRENCY_PRECEDENCE.index(quote)


def test_known_symbols_present():
    pairs = generate_pairs()
    for expected in ("EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"):
        assert expected in pairs


def test_split_pair_rejects_invalid_length():
    import pytest

    with pytest.raises(ValueError):
        split_pair("EURUS")


def test_with_broker_suffix():
    pairs = ["EURUSD", "USDJPY"]
    assert with_broker_suffix(pairs, "") == pairs
    assert with_broker_suffix(pairs, "m") == ["EURUSDm", "USDJPYm"]
