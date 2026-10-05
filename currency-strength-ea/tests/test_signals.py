import numpy as np
import pandas as pd

from src.signals import SignalParams, candidate_events, dominance_counts, pair_zscore

KW = dict(vol_lookback=5, vol_min_periods=5)  # janelas pequenas só para o teste


def _walk(n, start="2024-01-02T00:00", seed=0, step=0.0005):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    return pd.Series(1.1 * np.exp(np.cumsum(rng.normal(0, step, n))), index=idx)


def test_z_anti_lookahead_close_de_T_nao_afeta_z_de_T():
    """Mudar o close de um candle não pode mudar z em nenhuma linha até e
    incluindo a dele — o z em T só pode usar fechamentos até T-1."""
    base = _walk(120)
    pert = base.copy()
    pert.iloc[80] = base.iloc[80] * 1.5  # choque enorme só no candle 80
    z_a, s_a = pair_zscore(base, "daily", **KW)
    z_b, s_b = pair_zscore(pert, "daily", **KW)
    pd.testing.assert_series_equal(z_a.iloc[:81], z_b.iloc[:81])
    pd.testing.assert_series_equal(s_a.iloc[:81], s_b.iloc[:81])
    assert not np.isclose(z_a.iloc[81], z_b.iloc[81])  # candle 81 já enxerga o 80


def test_z_confere_formula_na_mao():
    # c0 está na janela do dia anterior (ancora o preço-base); c1.. abrem 2024-01-02.
    close = _walk(14, start="2024-01-01T23:55", seed=1)
    z, sigma = pair_zscore(close, "daily", **KW)
    lc = np.log(close.to_numpy())
    T = 9
    first = 1
    r_acc = lc[T - 1] - lc[first - 1]        # prev_close(T) - preço-base (prev_close da 1ª linha)
    n = T - first
    lr = np.diff(lc, prepend=np.nan)
    sig = np.std(lr[T - 5 : T], ddof=1)      # retornos de T-5..T-1 (shift(1) da rolling)
    assert np.isclose(sigma.iloc[T], sig)
    assert np.isclose(z.iloc[T], r_acc / (sig * np.sqrt(n)))


def test_gap_encerra_segmento_e_rebaseia_depois():
    pre = pd.date_range("2024-01-02T00:00", periods=12, freq="5min", tz="UTC")
    post = pd.date_range("2024-01-02T06:00", periods=14, freq="5min", tz="UTC")  # gap de ~5h > 2h
    idx = pre.append(post)
    rng = np.random.default_rng(3)
    close = pd.Series(1.1 * np.exp(np.cumsum(rng.normal(0, 0.0005, len(idx)))), index=idx)
    z, sigma = pair_zscore(close, "daily", **KW)
    g = 12  # 1º candle depois do gap
    assert z.iloc[g:g + 2].isna().all()  # g: baseline ainda não existe; g+1: n=0
    lc = np.log(close.to_numpy())
    # Linha T=g+8: base = fechamento do 1º candle pós-gap (g), nunca o pré-gap;
    # n = T - g - 1 passos; sigma já tem >=5 retornos pós-gap (o do gap é excluído).
    T = g + 8
    n = T - g - 1
    assert np.isfinite(sigma.iloc[T])
    assert np.isclose(z.iloc[T], (lc[T - 1] - lc[g]) / (sigma.iloc[T] * np.sqrt(n)))
    # O retorno que atravessa o gap (linha g) não pode entrar na estimativa de
    # sigma: com min_periods=4, em T=g+3 a janela cobre as linhas g-2..g+2 e
    # sigma tem de ser o std das 4 linhas SEM a g (se a g entrasse, seria outro valor).
    _, sigma4 = pair_zscore(close, "daily", vol_lookback=5, vol_min_periods=4)
    lr = np.diff(lc, prepend=np.nan)
    sem_gap = np.array([lr[g - 2], lr[g - 1], lr[g + 1], lr[g + 2]])
    com_gap = np.array([lr[g - 2], lr[g - 1], lr[g], lr[g + 1], lr[g + 2]])
    assert np.isclose(sigma4.iloc[g + 3], np.std(sem_gap, ddof=1))
    assert not np.isclose(sigma4.iloc[g + 3], np.std(com_gap, ddof=1))


def _universo3(z_rows, force=(0.01, 0.0, -0.01), ranks=(1, 2, 3)):
    idx = pd.date_range("2024-01-02T10:00", periods=len(z_rows), freq="5min", tz="UTC")
    z = pd.DataFrame(z_rows, index=idx, columns=["EURUSD", "EURJPY", "USDJPY"], dtype=float)
    sigma = pd.DataFrame(0.001, index=idx, columns=z.columns)
    force_a = pd.DataFrame([force] * len(idx), index=idx, columns=["EUR", "USD", "JPY"], dtype=float)
    rank_c = pd.DataFrame([ranks] * len(idx), index=idx, columns=["EUR", "USD", "JPY"], dtype=float)
    return z, sigma, force_a, rank_c


CCY3 = ["EUR", "USD", "JPY"]
P = SignalParams(k_min=2, z_crit=2.0)


def test_dominancia_conta_confrontos_significativos():
    z, *_ = _universo3([[3, 3, 3]])
    strong, weak = dominance_counts(z, 2.0, CCY3)
    assert strong.iloc[0].to_dict() == {"EUR": 2, "USD": 1, "JPY": 0}
    assert weak.iloc[0].to_dict() == {"EUR": 0, "USD": 1, "JPY": 2}


def test_onset_gera_um_evento_por_sinal_e_novo_evento_apos_reativar():
    #                 sem sinal     ativo         persiste      some          ativo de novo
    z, s, fa, rc = _universo3([[0, 0, 0], [3, 3, 3], [3, 3, 3], [0, 0, 0], [3, 3, 3]])
    ev = candidate_events(z, s, fa, rc, P, currencies=CCY3)
    assert len(ev) == 2  # persistência não duplica; reativação é novo onset
    first = ev.iloc[0]
    assert (first.pair, first.direction, first.strong_ccy, first.weak_ccy) == ("EURJPY", 1, "EUR", "JPY")
    assert first.n_strong == 2 and first.n_weak == 2
    assert np.isclose(first.force_gap, 0.02)
    assert first.rank_c_strong == 1 and first.rank_c_weak == 3
    assert ev.ts.iloc[0] == z.index[1] and ev.ts.iloc[1] == z.index[4]


def test_sinal_short_quando_a_cotada_e_a_forte():
    # JPY vence EUR e USD; EUR perde para USD e JPY -> EURJPY short, forte=JPY, fraca=EUR
    z, s, fa, rc = _universo3([[-3, -3, -3]], force=(-0.01, 0.0, 0.01), ranks=(3, 2, 1))
    ev = candidate_events(z, s, fa, rc, P, currencies=CCY3)
    assert len(ev) == 1
    e = ev.iloc[0]
    assert (e.pair, e.direction, e.strong_ccy, e.weak_ccy) == ("EURJPY", -1, "JPY", "EUR")


def test_prioridade_ordena_candidatos_simultaneos_pela_diferenca_de_forca():
    z, s, fa, rc = _universo3([[3, 3, 3]])
    ev = candidate_events(z, s, fa, rc, SignalParams(k_min=1, z_crit=2.0), currencies=CCY3)
    assert len(ev) == 3
    prio = dict(zip(ev.pair, ev.priority))
    assert prio["EURJPY"] == 1  # maior gap: EUR(0.01) - JPY(-0.01) = 0.02


def test_k_min_acima_do_alcancavel_nao_gera_evento():
    z, s, fa, rc = _universo3([[3, 3, 3]])
    ev = candidate_events(z, s, fa, rc, SignalParams(k_min=3, z_crit=2.0), currencies=CCY3)
    assert ev.empty


def test_z_abaixo_do_limiar_nao_gera_evento():
    z, s, fa, rc = _universo3([[1.9, 1.9, 1.9]])
    assert candidate_events(z, s, fa, rc, P, currencies=CCY3).empty
