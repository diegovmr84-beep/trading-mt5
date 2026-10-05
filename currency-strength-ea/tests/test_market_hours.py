import pandas as pd

from src.market_hours import in_rollover, market_closed, ny_local, us_dst


def _idx(*iso):
    return pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t in iso])


def test_horario_de_verao_dos_eua_fronteiras_exatas():
    # 2024: começa dom 10/mar às 07:00 UTC, termina dom 3/nov às 06:00 UTC
    idx = _idx("2024-03-10T06:59", "2024-03-10T07:00", "2024-11-03T05:59", "2024-11-03T06:00",
               "2024-07-01T12:00", "2024-01-15T12:00")
    assert list(us_dst(idx)) == [False, True, True, False, True, False]


def test_hora_local_de_ny():
    idx = _idx("2024-07-01T21:00", "2024-01-15T21:00")  # verão (UTC-4), inverno (UTC-5)
    assert list(ny_local(idx).hour) == [17, 16]


def test_rollover_acompanha_o_horario_de_verao():
    # 17:00 NY = 21:00 UTC no verão, 22:00 UTC no inverno; janela = 16:00-18:59 locais
    verao = _idx("2024-07-02T19:59", "2024-07-02T20:00", "2024-07-02T22:59", "2024-07-02T23:00")
    inverno = _idx("2024-01-02T20:59", "2024-01-02T21:00", "2024-01-02T23:59", "2024-01-03T00:00")
    assert list(in_rollover(verao)) == [False, True, True, False]
    assert list(in_rollover(inverno)) == [False, True, True, False]


def test_mercado_fechado_de_sexta_17h_a_domingo_17h_de_ny():
    # verão: fecha sex 21:00 UTC, abre dom 21:00 UTC
    idx = _idx("2024-07-05T20:59", "2024-07-05T21:00", "2024-07-06T12:00",
               "2024-07-07T20:59", "2024-07-07T21:00", "2024-07-08T10:00")
    assert list(market_closed(idx)) == [False, True, True, True, False, False]
