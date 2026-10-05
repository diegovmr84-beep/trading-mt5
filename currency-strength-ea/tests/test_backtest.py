import numpy as np
import pandas as pd
import pytest
from scipy import stats

from src import backtest_config as cfg
from src.backtest import apply_scenario, simulate_trades, tradable_mask
from src.validation_stats import cluster_mean_test, expectancy_r, select_config, verdict
from src.walkforward import make_folds

T0 = pd.Timestamp("2024-01-02T09:00", tz="UTC")  # terça, fora do rollover


def _ohlc(highs, lows, closes=None, opens=None, index=None):
    n = len(highs)
    idx = index if index is not None else pd.date_range(T0, periods=n, freq="5min")
    return pd.DataFrame(
        {
            "open": opens if opens is not None else [1.0] * n,
            "high": highs,
            "low": lows,
            "close": closes if closes is not None else [1.0] * n,
        },
        index=idx,
    )


def _event(direction=1, take=0.001, stop=0.002):
    return pd.DataFrame(
        {"ts": [T0], "pair": ["EURUSD"], "direction": [direction], "take_rel": [take], "stop_rel": [stop]}
    )


def _sim(df, ev, horizon=4):
    return simulate_trades(ev, {"EURUSD": df}, horizon=horizon).iloc[0]


def test_take_atingido():
    df = _ohlc(highs=[1.0005, 1.0008, 1.0012, 1.0], lows=[0.9995] * 4)
    r = _sim(df, _event())
    assert r.exit_reason == "take" and r.bars_held == 3 and np.isclose(r.gross_ret, 0.001)


def test_stop_atingido():
    df = _ohlc(highs=[1.0005] * 4, lows=[0.9995, 0.9970, 0.9995, 0.9995])
    r = _sim(df, _event())
    assert r.exit_reason == "stop" and r.bars_held == 2 and np.isclose(r.gross_ret, -0.002)


def test_stop_e_take_no_mesmo_candle_assume_stop():
    df = _ohlc(highs=[1.0005, 1.0020, 1.0, 1.0], lows=[0.9995, 0.9970, 1.0, 1.0])
    r = _sim(df, _event())
    assert r.exit_reason == "stop" and np.isclose(r.gross_ret, -0.002)


def test_saida_por_tempo_no_fechamento_do_ultimo_candle():
    df = _ohlc(highs=[1.0005] * 4, lows=[0.9995] * 4, closes=[1.0001, 1.0002, 1.0003, 1.0004])
    r = _sim(df, _event(), horizon=3)
    assert r.exit_reason == "time" and r.bars_held == 3
    assert np.isclose(r.gross_ret, np.log(1.0003 / 1.0))


def test_short_inverte_take_e_stop():
    df = _ohlc(highs=[1.0005] * 4, lows=[0.9995, 0.9985, 0.9980, 0.9995])
    r = _sim(df, _event(direction=-1))
    assert r.exit_reason == "take" and r.bars_held == 2 and np.isclose(r.gross_ret, 0.001)
    # mesma trajetória, mas short com stop apertado e preço subindo
    df2 = _ohlc(highs=[1.0005, 1.0030, 1.0, 1.0], lows=[0.9995] * 4)
    r2 = _sim(df2, _event(direction=-1))
    assert r2.exit_reason == "stop" and np.isclose(r2.gross_ret, -0.002)


def test_gap_no_horizonte_fecha_no_ultimo_candle_antes_do_gap():
    idx = pd.DatetimeIndex([T0, T0 + pd.Timedelta(minutes=5), T0 + pd.Timedelta(hours=6), T0 + pd.Timedelta(hours=6, minutes=5)])
    # depois do gap o preço dispararia o take, mas a posição não atravessa o gap
    df = _ohlc(highs=[1.0005, 1.0005, 1.0100, 1.0100], lows=[0.9995] * 4,
               closes=[1.0001, 1.0002, 1.0100, 1.0100], index=idx)
    r = _sim(df, _event(), horizon=4)
    assert r.exit_reason == "time" and r.bars_held == 2 and np.isclose(r.gross_ret, np.log(1.0002))


def test_cenario_aplica_custo_filtro_de_spread_e_rollover():
    base = pd.DataFrame(
        {
            "ts": [T0, T0, pd.Timestamp("2024-01-02T22:00", tz="UTC")],  # 3º: rollover (17h NY)
            "pair": "EURUSD",
            "gross_ret": [0.002, 0.002, 0.002],
            "stop_rel": 0.004,
            "take_rel": [0.002, 0.0005, 0.002],
            "spread_rel": [0.0001, 0.0001, 0.0001],
        }
    )
    ot = cfg.SCENARIOS["otimista"]
    pe = cfg.SCENARIOS["pessimista"]
    # otimista: 1x spread: 1e-4 <= 0.25*5e-4=1.25e-4 passa; rollover nunca passa
    assert list(tradable_mask(base, ot)) == [True, True, False]
    # pessimista: 3x spread = 3e-4 > 1.25e-4 reprova o take apertado
    assert list(tradable_mask(base, pe)) == [True, False, False]
    out = apply_scenario(base, pe)
    assert len(out) == 1
    assert np.isclose(out.cost_ret.iloc[0], 3.5 * 0.0001)  # 3x spread + 0,5 de slippage
    assert np.isclose(out.net_ret.iloc[0], 0.002 - 3.5e-4)


def test_cluster_com_clusters_unitarios_iguala_t_classico():
    rng = np.random.default_rng(0)
    r = rng.normal(0.001, 0.01, 60)
    res = cluster_mean_test(r, np.arange(60))
    ref = stats.ttest_1samp(r, 0.0)
    assert np.isclose(res.t, ref.statistic) and np.isclose(res.p_two, ref.pvalue)


def test_cluster_alarga_o_erro_quando_trades_do_cluster_sao_correlacionados():
    rng = np.random.default_rng(1)
    dias = rng.normal(0.0, 0.01, 30)
    r = np.repeat(dias, 5) + rng.normal(0, 0.0005, 150)   # 5 trades quase idênticos por dia
    cl = np.repeat(np.arange(30), 5)
    ingenuo = cluster_mean_test(r, np.arange(150))
    robusto = cluster_mean_test(r, cl)
    assert robusto.se > 1.8 * ingenuo.se  # tratar como independentes subestimaria muito o erro


def test_expectativa_em_r():
    assert np.isclose(expectancy_r(np.array([0.001, 0.003]), np.array([0.004, 0.004])), 0.5)


def _row(n, t, **kw):
    return {"n": n, "t": t, **kw}


def test_selecao_prefere_amostra_minima_e_cai_pra_maior_t_se_nenhuma_atinge():
    rows = [_row(50, 9.0, id="a"), _row(cfg.N_MIN_TRADES, 2.0, id="b"), _row(300, 1.0, id="c")]
    assert select_config(rows)["id"] == "b"
    assert select_config([_row(10, 1.0, id="x"), _row(20, 3.0, id="y")])["id"] == "y"


def _summ(mean_bps=5.0, n=500, p_two=1e-6, p_one=1e-6, exp_r=0.2):
    return {"mean_bps": mean_bps, "n": n, "p_two": p_two, "p_one_pos": p_one, "exp_R": exp_r}


def test_veredicto():
    v, _ = verdict(_summ(), _summ(), wf_mean=1.0)
    assert v == "validado"
    assert verdict(_summ(), _summ(mean_bps=-1.0), 1.0)[0] == "não validado"
    assert verdict(_summ(mean_bps=-1.0), _summ(), 1.0)[0] == "não validado"
    v, why = verdict(_summ(n=30), _summ(), 1.0)
    assert v == "preliminar" and any("amostra" in w for w in why)
    v, why = verdict(_summ(p_two=0.01), _summ(), 1.0)  # não passa no Bonferroni (0.05/63)
    assert v == "preliminar" and any("Bonferroni" in w for w in why)
    assert verdict(_summ(), _summ(), wf_mean=-0.5)[0] == "preliminar"
    # sem abrir o OOS: sem edge in-sample já é "não validado"; com edge fica "preliminar"
    assert verdict(_summ(mean_bps=-0.5), None, 1.0)[0] == "não validado"
    assert verdict(_summ(), None, 1.0) == ("preliminar", ["validação (out-of-sample) ainda não aberta"])


def test_contagem_de_bonferroni_e_9_configs_vezes_7_comparacoes_internas():
    assert cfg.M_TESTS == 63 and np.isclose(cfg.ALPHA_BONFERRONI, 0.05 / 63)


def test_dobras_do_walk_forward_respeitam_embargo_e_nao_tocam_validacao():
    cutoff = pd.Timestamp("2024-09-24T13:44", tz="UTC")
    embargo = 6 * 3600
    folds = make_folds(pd.Timestamp("2020-01-03", tz="UTC"), cutoff, embargo)
    assert folds[0][0] == pd.Timestamp("2020-01-01", tz="UTC")           # começa no 1º dia do mês
    for train_start, train_end, test_end in folds:
        assert train_end - train_start >= pd.Timedelta(days=180)         # ~6 meses de treino
        assert test_end + pd.Timedelta(seconds=embargo) <= cutoff        # teste nunca invade a validação
    starts = [f[0] for f in folds]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)  # desliza 1 mês por vez


def test_validacao_so_pode_ser_aberta_uma_vez(tmp_path):
    from src import db
    from src.backtest_io import ValidationAlreadyOpenedError, open_validation_lock

    conn = db.connect(tmp_path / "t.db")
    open_validation_lock(conn, "session_k6")
    with pytest.raises(ValidationAlreadyOpenedError):
        open_validation_lock(conn, "overlap_k5")
    assert conn.execute("SELECT COUNT(*) FROM validation_lock").fetchone()[0] == 1
    conn.close()
