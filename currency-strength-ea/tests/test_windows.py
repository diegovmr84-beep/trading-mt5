import pandas as pd
import pytest

from src.windows import WINDOW_VARIANTS, window_anchor


def _idx(*timestamps_iso):
    return pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t in timestamps_iso])


def test_daily_reseta_meia_noite_utc():
    idx = _idx("2024-01-01T00:00", "2024-01-01T13:30", "2024-01-01T23:55", "2024-01-02T00:00")
    anchors = window_anchor(idx, "daily")
    assert list(anchors) == [
        pd.Timestamp("2024-01-01T00:00", tz="UTC"),
        pd.Timestamp("2024-01-01T00:00", tz="UTC"),
        pd.Timestamp("2024-01-01T00:00", tz="UTC"),
        pd.Timestamp("2024-01-02T00:00", tz="UTC"),
    ]


def test_overlap_reseta_as_13utc_e_usa_dia_anterior_antes_disso():
    idx = _idx("2024-01-01T12:59", "2024-01-01T13:00", "2024-01-01T20:00", "2024-01-02T05:00")
    anchors = list(window_anchor(idx, "overlap"))
    assert anchors[0] == pd.Timestamp("2023-12-31T13:00", tz="UTC")
    assert anchors[1] == pd.Timestamp("2024-01-01T13:00", tz="UTC")
    assert anchors[2] == pd.Timestamp("2024-01-01T13:00", tz="UTC")
    assert anchors[3] == pd.Timestamp("2024-01-01T13:00", tz="UTC")  # ainda antes das 13h do dia 2


def test_session_reseta_em_0_8_13_utc():
    idx = _idx("2024-01-01T00:00", "2024-01-01T07:59", "2024-01-01T08:00",
               "2024-01-01T12:59", "2024-01-01T13:00", "2024-01-01T23:59")
    anchors = list(window_anchor(idx, "session"))
    expected_hours = [0, 0, 8, 8, 13, 13]
    for a, h in zip(anchors, expected_hours):
        assert a == pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(hours=h)


def test_todas_as_variantes_documentadas_sao_suportadas():
    idx = _idx("2024-06-15T10:00")
    for variant in WINDOW_VARIANTS:
        window_anchor(idx, variant)  # não deve levantar


def test_variante_desconhecida_levanta():
    with pytest.raises(ValueError):
        window_anchor(_idx("2024-01-01T00:00"), "mensal")
