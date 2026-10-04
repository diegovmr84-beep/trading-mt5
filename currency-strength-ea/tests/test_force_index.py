import numpy as np
import pandas as pd

from src.force_index import compute_force_index, compute_pair_return, force_index_to_rows


def _series(values, start="2024-01-01T00:00", freq="5min"):
    idx = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx)


def test_retorno_nao_usa_close_do_proprio_candle():
    """Anti-lookahead (Seção 3.2): o retorno atribuído ao candle T não pode
    depender do close de T, só dos candles anteriores — senão o índice
    "veria o futuro" no momento em que é publicado."""
    base = _series([1.0, 1.0005, 1.0010, 1.0015, 1.0020, 1.0025])
    perturbed = base.copy()
    perturbed.iloc[3] = 999.0  # mexe só no close do candle de índice 3

    ret_base = compute_pair_return(base, "daily")
    ret_pert = compute_pair_return(perturbed, "daily")

    # Índices 0..3: nada pode ter mudado (retorno em T não usa close[T]).
    pd.testing.assert_series_equal(ret_base.iloc[:4], ret_pert.iloc[:4])
    # Índice 4 usa prev_close = close[3], que mudou — aqui DEVE divergir,
    # senão o teste acima seria vácuo (não estaria testando nada real).
    assert not np.isclose(ret_base.iloc[4], ret_pert.iloc[4])


def test_retorno_primeiro_candle_da_serie_e_nan():
    """Sem candle anterior, não há preço-base conhecido — não inventa dado."""
    s = _series([1.0, 1.1, 1.2])
    ret = compute_pair_return(s, "daily")
    assert np.isnan(ret.iloc[0])


def test_retorno_zera_no_primeiro_candle_de_cada_janela_e_acumula_dentro_dela():
    # seed no dia anterior (ancora a janela do dia seguinte), depois 3 candles no mesmo dia.
    s = _series([1.0000, 1.0000, 1.0010, 1.0020], start="2023-12-31T23:55")
    ret = compute_pair_return(s, "daily")
    # seed: NaN (sem anterior) | t0 (abre a janela de 2024-01-01): retorno 0
    assert np.isnan(ret.iloc[0])
    assert ret.iloc[1] == 0.0
    assert np.isclose(ret.iloc[2], 1.0000 / 1.0000 - 1)  # prev_close=1.0000, baseline=1.0000
    assert np.isclose(ret.iloc[3], 1.0010 / 1.0000 - 1)  # prev_close=1.0010, baseline=1.0000


def test_forca_metodo_a_decompoe_base_e_cotada_com_sinais_opostos():
    """Universo reduzido (3 moedas, 3 pares) pra conferir a conta na mão:
    EUR aparece como base em 2 pares, USD como base em 1 e cotada em 1,
    JPY como cotada em 2 — exatamente a mecânica da Seção 3.0."""
    eurusd = _series([1.0000, 1.0000, 1.0010, 1.0020], start="2023-12-31T23:55")
    eurjpy = _series([150.00, 150.00, 150.15, 150.30], start="2023-12-31T23:55")
    usdjpy = _series([151.00, 151.00, 150.85, 150.70], start="2023-12-31T23:55")
    closes = {"EURUSD": eurusd, "EURJPY": eurjpy, "USDJPY": usdjpy}

    force_a, rank_c = compute_force_index(closes, "daily", currencies=["EUR", "USD", "JPY"])

    # index: 0=23:55(seed) 1=00:00(abre a janela, retorno 0) 2=00:05(prev_close
    # ainda é o de 00:00 -> retorno 0) 3=00:10 (prev_close agora é o de 00:05,
    # primeiro ponto em que a mudança de preço aparece — efeito do shift
    # anti-lookahead, um candle de atraso por construção).
    t3 = force_a.index[3]
    ret_eurusd = 1.0010 / 1.0000 - 1
    ret_eurjpy = 150.15 / 150.00 - 1
    ret_usdjpy = 150.85 / 151.00 - 1

    expected_eur = (ret_eurusd + ret_eurjpy) / 2       # base nos dois pares
    expected_usd = (-ret_eurusd + ret_usdjpy) / 2      # cotada em EURUSD, base em USDJPY
    expected_jpy = (-ret_eurjpy + -ret_usdjpy) / 2     # cotada nos dois pares

    assert np.isclose(force_a.loc[t3, "EUR"], expected_eur)
    assert np.isclose(force_a.loc[t3, "USD"], expected_usd)
    assert np.isclose(force_a.loc[t3, "JPY"], expected_jpy)

    # EUR é claramente a mais forte nesse timestamp -> rank 1 (Método C concorda com A).
    assert rank_c.loc[t3, "EUR"] == 1.0
    assert force_a.loc[t3, "EUR"] > force_a.loc[t3, "JPY"] > force_a.loc[t3, "USD"]


def test_metodo_c_diverge_de_a_quando_a_e_dominado_por_outlier():
    """O motivo de existir o Método C (Seção 3.1): um par com movimento gigante
    pode dominar a média do Método A mesmo que a moeda esteja perdendo nos
    outros confrontos. EUR aqui tem 1 vitória enorme (+1%) e 1 derrota
    pequena (-0.01%) contra JPY — Método A acha EUR claramente mais forte;
    Método C (placar de vitórias/derrotas, 1 a 1 pra EUR e também 1 a 1 pra
    JPY e USD) não consegue distinguir as três — empate de verdade."""
    eurusd = _series([1.0000, 1.0000, 1.0100, 1.0100], start="2023-12-31T23:55")  # +1% (EUR ganha grande)
    eurjpy = _series([150.0000, 150.0000, 149.9850, 149.9850], start="2023-12-31T23:55")  # -0.01% (EUR perde pequeno)
    usdjpy = _series([151.0000, 151.0000, 151.0151, 151.0151], start="2023-12-31T23:55")  # +0.01% (USD ganha pequeno)
    closes = {"EURUSD": eurusd, "EURJPY": eurjpy, "USDJPY": usdjpy}

    force_a, rank_c = compute_force_index(closes, "daily", currencies=["EUR", "USD", "JPY"])
    t3 = force_a.index[3]

    # Método A: EUR muito na frente, por causa do outlier de +1%.
    assert force_a.loc[t3, "EUR"] > force_a.loc[t3, "JPY"] > force_a.loc[t3, "USD"]
    assert force_a.loc[t3, "EUR"] > 0.004  # dominado pelo +1% dividido por 2 pares

    # Método C: cada moeda ganhou 1 e perdeu 1 confronto -> placar 0 pras três
    # -> empate real, rank "average" dá a mesma posição (2.0) pras três.
    assert rank_c.loc[t3, "EUR"] == rank_c.loc[t3, "USD"] == rank_c.loc[t3, "JPY"] == 2.0


def test_moeda_sem_nenhum_par_fica_de_fora_sem_quebrar():
    eurusd = _series([1.0, 1.0, 1.001], start="2023-12-31T23:55")
    force_a, rank_c = compute_force_index({"EURUSD": eurusd}, "daily", currencies=["EUR", "USD", "JPY"])
    assert "JPY" not in force_a.columns  # nenhum par com JPY foi passado
    assert set(force_a.columns) == {"EUR", "USD"}


def test_force_index_to_rows_pula_nan_e_preserva_valores():
    force_a = pd.DataFrame(
        {"EUR": [0.001, np.nan]}, index=pd.date_range("2024-01-01", periods=2, freq="5min", tz="UTC")
    )
    rank_c = pd.DataFrame(
        {"EUR": [1.0, np.nan]}, index=force_a.index
    )
    rows = force_index_to_rows(force_a, rank_c, "daily")
    assert len(rows) == 1  # a linha NaN foi descartada
    ts, variant, currency, fa, rc = rows[0]
    assert variant == "daily" and currency == "EUR"
    assert np.isclose(fa, 0.001) and rc == 1.0
    assert ts == 1704067200  # 2024-01-01T00:00:00Z em epoch segundos — não "1" nem microssegundos


def test_force_index_to_rows_epoch_correto_em_qualquer_resolucao_do_indice():
    """Regressão: pandas >=2 preserva a resolução de origem do DatetimeIndex
    (visto rodando: o índice carregado da Fase 1 via `pd.to_datetime(...,
    unit='s')` vem em resolução 's', não 'ns') — `.astype(int64) // 10**9`
    supondo nanossegundos colapsou timestamps reais de 2020-2026 todos pra
    epoch=1 silenciosamente (sem erro, só dado errado gravado no banco)."""
    idx_segundos = pd.DatetimeIndex(pd.to_datetime(pd.Series([1704067200]), unit="s", utc=True))
    assert idx_segundos.dtype == "datetime64[s, UTC]"
    force_a = pd.DataFrame({"EUR": [0.001]}, index=idx_segundos)
    rank_c = pd.DataFrame({"EUR": [1.0]}, index=idx_segundos)
    rows = force_index_to_rows(force_a, rank_c, "daily")
    assert rows[0][0] == 1704067200
