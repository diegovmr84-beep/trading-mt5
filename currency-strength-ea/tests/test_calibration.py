import numpy as np
import pandas as pd
import pytest

from src import db
from src.calibration import (
    CalibrationParams,
    apply_calibration,
    assign_bucket,
    bucket_edges,
    calibrate_stop_take,
    embargo_seconds,
    forward_excursions,
)
from src.spread_model import SpreadParams, apply_spread_filter, spread_table
from src.split import ValidationLeakError, dev_cutoff


def _ohlc(opens, highs, lows, start="2024-01-02T10:00"):
    idx = pd.date_range(start, periods=len(opens), freq="5min", tz="UTC")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows}, index=idx)


def test_dev_cutoff_70_por_cento_do_intervalo():
    assert dev_cutoff(0, 1000) == 700
    assert dev_cutoff(1000, 2000) == 1700


def test_excursoes_long_e_short_na_mao():
    df = _ohlc([100, 101, 102, 103], [101, 103, 102, 110], [99, 98, 100, 90])
    pos = np.array([0])
    mfe, mae = forward_excursions(df, pos, np.array([1]), horizon=3, max_span_s=10_000)
    assert np.isclose(mfe[0], np.log(103 / 100))  # max high nas linhas 0..2 = 103
    assert np.isclose(mae[0], np.log(100 / 98))   # min low nas linhas 0..2 = 98
    mfe_s, mae_s = forward_excursions(df, pos, np.array([-1]), horizon=3, max_span_s=10_000)
    assert np.isclose(mfe_s[0], np.log(100 / 98))  # short: favorável = queda
    assert np.isclose(mae_s[0], np.log(103 / 100))


def test_excursao_nan_sem_candles_suficientes_ou_com_gap_na_janela():
    df = _ohlc([100, 101, 102], [101, 102, 103], [99, 100, 101])
    mfe, mae = forward_excursions(df, np.array([2]), np.array([1]), horizon=3, max_span_s=10_000)
    assert np.isnan(mfe[0]) and np.isnan(mae[0])  # faltam candles à frente

    idx = pd.DatetimeIndex(
        ["2024-01-02T10:00", "2024-01-02T10:05", "2024-01-02T15:00"], tz="UTC"
    )
    gap = pd.DataFrame({"open": [1.0, 1, 1], "high": [1.1, 1.1, 1.1], "low": [0.9, 0.9, 0.9]}, index=idx)
    mfe, _ = forward_excursions(gap, np.array([0]), np.array([1]), horizon=3, max_span_s=3 * 300 * 2)
    assert np.isnan(mfe[0])  # gap de ~5h dentro da janela de 3 candles


def _events(zs, ts_start="2023-06-01", mfe=1.0, mae=0.5):
    n = len(zs)
    return pd.DataFrame(
        {
            "ts": pd.date_range(ts_start, periods=n, freq="1h", tz="UTC"),
            "pair": "EURUSD",
            "z_pair": zs,
            "sigma1": 0.001,
            "mfe_z": np.linspace(0.5, 1.5, n) * mfe,
            "mae_z": np.linspace(0.2, 0.8, n) * mae,
        }
    )


def test_calibracao_recusa_evento_de_validacao():
    ev = _events(np.linspace(2, 4, 40))
    cutoff = int(pd.Timestamp("2023-06-01T10:00", tz="UTC").timestamp())  # corta no meio dos eventos
    with pytest.raises(ValidationLeakError):
        calibrate_stop_take(ev, cutoff, CalibrationParams(n_buckets=4))


def test_calibracao_recusa_evento_cujo_resultado_invade_a_validacao():
    """Embargo: evento ANTES do corte, mas perto o bastante para a janela de
    MFE/MAE cruzar o corte, também não pode calibrar (usaria preço de validação)."""
    params = CalibrationParams(horizon=36)
    cutoff = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp())
    perto = cutoff - embargo_seconds(params) // 2          # dentro do embargo
    longe = cutoff - embargo_seconds(params) - 3600        # fora do embargo
    ev = _events(np.linspace(2, 4, 8))
    ev["ts"] = pd.to_datetime([longe, longe, longe, longe, longe, longe, longe, perto], unit="s", utc=True)
    with pytest.raises(ValidationLeakError):
        calibrate_stop_take(ev, cutoff, params)
    ev.loc[ev.index[-1], "ts"] = pd.Timestamp(longe, unit="s", tz="UTC")
    calibrate_stop_take(ev, cutoff, CalibrationParams(horizon=36, n_buckets=2))  # sem o evento em embargo, passa


def test_calibracao_so_dev_gera_tabela_e_buckets_cobrem_tudo():
    ev = _events(np.linspace(2, 4, 40))
    cutoff = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp())
    params = CalibrationParams(horizon=36, q_take=0.5, q_stop=0.75, n_buckets=4)
    table = calibrate_stop_take(ev, cutoff, params)
    assert list(table.bucket) == [0, 1, 2, 3]
    assert table.n_events.sum() == 40
    assert table.z_lo.iloc[0] == -np.inf and table.z_hi.iloc[-1] == np.inf
    # intensidade maior -> mfe maior nesse dado sintético -> take cresce com o bucket
    assert table.take_z.is_monotonic_increasing

    # eventos "de validação" com intensidade fora da faixa de dev: caem no bucket extremo
    val = pd.DataFrame({"z_pair": [10.0, 0.1], "sigma1": [0.001, 0.001]})
    out = apply_calibration(val, table, horizon=36)
    assert list(out.bucket) == [3, 0]
    assert np.isclose(out.take_rel.iloc[0], table.take_z.iloc[3] * 0.001 * 6)


def test_bordas_de_bucket_vem_dos_quantis_de_dev():
    edges = bucket_edges(np.arange(1.0, 101.0), 4)
    assert edges[0] == -np.inf and edges[-1] == np.inf
    assert np.isclose(edges[2], np.quantile(np.arange(1.0, 101.0), 0.5))
    assert list(assign_bucket(np.array([1.0, 50.0, 100.0]), edges)) == [0, 1, 3]


def test_filtro_de_spread_compara_com_distancia_do_take(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    # spread relativo constante = 0.0002/1.1 ~ 1.82e-4 em 'london'
    terca_9h = int(pd.Timestamp("2024-01-02T09:00", tz="UTC").timestamp())  # mercado aberto, fora do rollover
    sabado = int(pd.Timestamp("2024-01-06T09:00", tz="UTC").timestamp())     # mercado fechado: cotação congelada
    rollover = int(pd.Timestamp("2024-01-02T22:00", tz="UTC").timestamp())   # 17:00 NY (inverno) = 22:00 UTC
    rows = [(sid, terca_9h + i * 30, "london", 1.0999, 1.1001, 0.0002) for i in range(20)]
    # amostras absurdamente largas em fim de semana e rollover NÃO podem entrar na tabela
    rows += [(sid, sabado + i * 30, "london", 1.0900, 1.1100, 0.02) for i in range(20)]
    rows += [(sid, rollover + i * 30, "london", 1.0900, 1.1100, 0.02) for i in range(20)]
    db.insert_spread_samples(conn, rows)
    table = spread_table(conn, 0.75)
    assert np.isclose(table[("EURUSD", "london")], 0.0002 / 1.1)

    ts = pd.Timestamp("2024-01-02T09:00", tz="UTC")  # hora 9 UTC -> sessão london
    ev = pd.DataFrame(
        {
            "ts": [ts, ts, ts],
            "pair": ["EURUSD", "EURUSD", "GBPUSD"],
            "take_rel": [0.002, 0.0003, 0.002],  # folgado / apertado / par sem amostra
        }
    )
    out = apply_spread_filter(ev, table, SpreadParams(quantile=0.75, max_spread_to_take=0.25))
    assert list(out.session) == ["london"] * 3
    # 0.25*0.002 = 5e-4 >= 1.82e-4 ok; 0.25*0.0003 = 7.5e-5 < 1.82e-4 reprova; sem amostra reprova
    assert list(out.spread_ok) == [True, False, False]

    # Mesmo com take folgado, evento no rollover nunca é operável.
    ev_roll = pd.DataFrame({"ts": [pd.Timestamp("2024-01-02T22:00", tz="UTC")], "pair": ["EURUSD"], "take_rel": [0.05]})
    out = apply_spread_filter(ev_roll, table.rename_axis(["pair", "session"]), SpreadParams())
    assert bool(out.rollover.iloc[0]) and not bool(out.spread_ok.iloc[0])
    conn.close()
