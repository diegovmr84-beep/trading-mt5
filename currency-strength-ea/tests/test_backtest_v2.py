import numpy as np
import pandas as pd
import pytest

from src import backtest_config as cfg
from src import preregistration_v2 as v2
from src.backtest_v2 import (
    apply_scenario_v2,
    robustness_checks,
    simulate_time_exit,
    verdict_v2,
)

T0 = pd.Timestamp("2024-01-02T09:00", tz="UTC")


def _ohlc(opens, highs, lows, closes, index=None):
    idx = index if index is not None else pd.date_range(T0, periods=len(opens), freq="5min")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)


def _ev(direction=1):
    return pd.DataFrame({"ts": [T0], "pair": ["EURUSD"], "direction": [direction]})


def test_fade_de_sinal_long_vira_short_e_ganha_quando_o_preco_cai():
    df = _ohlc([1.0] * 4, [1.0005, 1.0010, 1.0002, 1.0001], [0.9990, 0.9970, 0.9960, 0.9950], [0.999, 0.998, 0.997, 0.996])
    r = simulate_time_exit(_ev(direction=1), {"EURUSD": df}, horizon=4).iloc[0]
    assert r.exit_reason == "time" and r.bars_held == 4
    assert np.isclose(r.gross_ret, np.log(1.0 / 0.996))  # short: ganha quando fecha em 0.996
    # pior excursão adversa de um short = máxima acima da entrada: log(1.0010/1.0)
    assert np.isclose(r.mae, np.log(1.0010 / 1.0))


def test_sem_fade_segue_o_sinal():
    df = _ohlc([1.0] * 3, [1.001] * 3, [0.999] * 3, [1.0005, 1.001, 1.002])
    r = simulate_time_exit(_ev(direction=1), {"EURUSD": df}, horizon=3, fade=False).iloc[0]
    assert np.isclose(r.gross_ret, np.log(1.002))


def test_gap_fecha_no_ultimo_candle_antes_do_gap():
    idx = pd.DatetimeIndex([T0, T0 + pd.Timedelta(minutes=5), T0 + pd.Timedelta(hours=8), T0 + pd.Timedelta(hours=8, minutes=5)])
    df = _ohlc([1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 0.5, 0.5], [1.0, 0.9990, 0.5, 0.5], index=idx)
    r = simulate_time_exit(_ev(direction=1), {"EURUSD": df}, horizon=4).iloc[0]
    assert r.exit_reason == "gap" and r.bars_held == 2
    assert np.isclose(r.gross_ret, np.log(1.0 / 0.9990))  # short ganha 10 bps; o desabamento pós-gap não entra


def test_cenario_exclui_rollover_e_desconta_custo():
    base = pd.DataFrame(
        {
            "ts": [T0, pd.Timestamp("2024-01-02T22:00", tz="UTC")],  # 2º no rollover
            "pair": "EURUSD",
            "gross_ret": [0.0040, 0.0040],
            "spread_rel": [0.0001, 0.0001],
        }
    )
    out = apply_scenario_v2(base, cfg.SCENARIOS["realista"])
    assert len(out) == 1
    assert np.isclose(out.net_ret.iloc[0], 0.0040 - 2 * 0.0001)


def _tr(pairs, rets, start=T0):
    return pd.DataFrame(
        {"ts": [start + pd.Timedelta(days=i) for i in range(len(rets))], "pair": pairs, "net_ret": rets}
    )


def test_robustez_sem_par_mais_frequente_e_metades():
    t = _tr(["AUDJPY"] * 4 + ["EURUSD"] * 2, [0.005, 0.005, -0.001, -0.001, 0.002, 0.002])
    rob = robustness_checks(t)
    assert rob["top_pair"] == "AUDJPY" and np.isclose(rob["top_pair_share"], 4 / 6)
    assert np.isclose(rob["mean_bps_without_top_pair"], 20.0)
    assert rob["mean_bps_first_half"] > rob["mean_bps_second_half"]


def _oos(mean=10.0, n=275, p=0.01):
    return {"n": n, "mean_bps": mean, "p_one_pos": p}


def _rob(without_top=5.0, h1=8.0, h2=12.0):
    return {"mean_bps_without_top_pair": without_top, "mean_bps_first_half": h1, "mean_bps_second_half": h2}


def test_veredito_v2():
    assert verdict_v2(_oos(), _rob())[0] == "validado"
    assert verdict_v2(_oos(mean=-0.1), _rob())[0] == "não validado"
    assert verdict_v2({"n": 0}, _rob())[0] == "não validado"
    for kw in (dict(p=0.2), dict(n=50), dict(mean=3.0)):
        v, why = verdict_v2(_oos(**kw), _rob())
        assert v == "preliminar" and why
    assert verdict_v2(_oos(), _rob(without_top=-1.0))[0] == "preliminar"   # só o AUDJPY sustentava
    assert verdict_v2(_oos(), _rob(h1=-2.0))[0] == "preliminar"            # efeito em uma metade só


def test_preregistro_v2_constantes():
    assert v2.HORIZON_CANDLES == 288 and v2.K_PRIMARY == 5 and v2.PRIMARY_SCENARIO in cfg.SCENARIOS
