# Triagem de custo vs. volatilidade (descritivo, só desenvolvimento)

Período: até 2024-09-24. Só custo e volatilidade; nenhum retorno de estratégia, nenhum OOS. Custo realista = 2× o spread medido (piso da conta Trial; em conta real pode ser maior). Retorno de h candles em janelas contíguas, entrada fora do rollover.

**Como ler:** `razão` = custo ÷ movimento típico. `hit mín` = taxa de acerto que uma aposta direcional simétrica precisaria só para empatar depois do custo. Razão baixa = o custo pesa pouco; **não** significa que há edge — só que, se houver, o custo não o come.

## Por par (ordenado pela razão em 4h)

| par | faixa | spread (bps) | mov. 1h (bps) | mov. 4h (bps) | mov. 24h (bps) | razão 1h | razão 4h | razão 24h | hit mín 1h | hit mín 4h | hit mín 24h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| USDJPY | B | 0.64 | 7.4 | 15.2 | 40.4 | 0.172 | 0.084 | 0.032 | 58.6% | 54.2% | 51.6% |
| GBPUSD | B | 0.75 | 8.2 | 16.7 | 41.6 | 0.182 | 0.089 | 0.036 | 59.1% | 54.5% | 51.8% |
| AUDJPY | B | 0.99 | 10.5 | 21.0 | 54.0 | 0.189 | 0.094 | 0.037 | 59.5% | 54.7% | 51.8% |
| EURUSD | C | 0.70 | 6.8 | 13.9 | 34.8 | 0.206 | 0.101 | 0.040 | 60.3% | 55.0% | 52.0% |
| CADJPY | C | 0.99 | 9.0 | 18.4 | 47.7 | 0.220 | 0.107 | 0.041 | 61.0% | 55.4% | 52.1% |
| EURJPY | C | 0.89 | 7.8 | 16.1 | 39.4 | 0.229 | 0.111 | 0.045 | 61.4% | 55.6% | 52.3% |
| GBPJPY | C | 1.05 | 9.0 | 18.5 | 45.0 | 0.235 | 0.114 | 0.047 | 61.7% | 55.7% | 52.3% |
| AUDUSD | C | 1.26 | 10.3 | 20.8 | 53.0 | 0.245 | 0.121 | 0.048 | 62.2% | 56.1% | 52.4% |
| GBPNZD | C | 1.03 | 7.9 | 15.8 | 35.4 | 0.262 | 0.130 | 0.058 | 63.1% | 56.5% | 52.9% |
| EURAUD | C | 1.05 | 7.9 | 16.0 | 40.2 | 0.267 | 0.131 | 0.052 | 63.3% | 56.6% | 52.6% |
| GBPCAD | C | 0.96 | 6.9 | 14.1 | 32.4 | 0.280 | 0.136 | 0.059 | 64.0% | 56.8% | 53.0% |
| EURNZD | C | 1.10 | 7.9 | 16.0 | 38.4 | 0.279 | 0.138 | 0.057 | 63.9% | 56.9% | 52.9% |
| GBPAUD | C | 1.11 | 7.8 | 15.6 | 36.6 | 0.285 | 0.143 | 0.061 | 64.2% | 57.1% | 53.0% |
| EURCAD | C | 0.93 | 6.3 | 12.9 | 32.3 | 0.297 | 0.145 | 0.058 | 64.9% | 57.2% | 52.9% |
| CHFJPY | C | 1.11 | 7.2 | 14.9 | 33.1 | 0.306 | 0.148 | 0.067 | 65.3% | 57.4% | 53.3% |
| USDCAD | C | 1.01 | 6.5 | 13.2 | 32.8 | 0.309 | 0.153 | 0.061 | 65.4% | 57.6% | 53.1% |
| NZDJPY | C | 1.56 | 10.2 | 20.3 | 52.8 | 0.306 | 0.154 | 0.059 | 65.3% | 57.7% | 53.0% |
| AUDCHF | C | 1.54 | 9.0 | 18.2 | 44.8 | 0.343 | 0.170 | 0.069 | 67.2% | 58.5% | 53.4% |
| GBPCHF | C | 1.37 | 7.1 | 14.9 | 34.3 | 0.382 | 0.184 | 0.080 | 69.1% | 59.2% | 54.0% |
| CADCHF | C | 1.36 | 7.2 | 14.7 | 35.9 | 0.377 | 0.186 | 0.076 | 68.9% | 59.3% | 53.8% |
| USDCHF | C | 1.58 | 7.1 | 14.4 | 35.7 | 0.448 | 0.220 | 0.089 | 72.4% | 61.0% | 54.4% |
| NZDUSD | C | 2.44 | 10.3 | 20.6 | 52.0 | 0.474 | 0.237 | 0.094 | 73.7% | 61.9% | 54.7% |
| AUDCAD | C | 1.81 | 7.1 | 14.3 | 34.7 | 0.507 | 0.254 | 0.104 | 75.4% | 62.7% | 55.2% |
| EURGBP | C | 1.52 | 5.8 | 11.9 | 28.7 | 0.523 | 0.254 | 0.106 | 76.2% | 62.7% | 55.3% |
| NZDCAD | C | 2.24 | 7.5 | 14.9 | 36.4 | 0.597 | 0.302 | 0.123 | 79.8% | 65.1% | 56.2% |
| AUDNZD | C | 1.45 | 4.9 | 9.6 | 25.0 | 0.589 | 0.304 | 0.116 | 79.4% | 65.2% | 55.8% |
| NZDCHF | C | 2.97 | 8.8 | 17.6 | 44.3 | 0.673 | 0.338 | 0.134 | 83.6% | 66.9% | 56.7% |
| EURCHF | C | 1.70 | 4.9 | 10.0 | 24.0 | 0.694 | 0.340 | 0.141 | 84.7% | 67.0% | 57.1% |

Faixas (razão 4h): A (≤ 0.06) = 0 · B (≤ 0.1) = 3 · C = 25.
**Aviso:** os cortes 0,06/0,10 foram herdados da `spread_analysis` (custo de 1× spread sobre um take de 0,9·sigma·√36); aqui o custo é 2× e o denominador é outro, então quase tudo cai na faixa C e as faixas não discriminam. Use a **ordem** dos pares e as colunas `hit mín`, não as letras.

## Razão por horizonte (mediana dos 28 pares)

| horizonte | razão mediana | hit mín mediano |
|---|---|---|
| 1h | 0.301 | 65.1% |
| 4h | 0.147 | 57.3% |
| 24h | 0.060 | 53.0% |

## Movimento típico de 1h por sessão (bps) e razão custo/movimento

Sessões em UTC fixo (sem ajuste de horário de verão). Spread da Trial é constante entre sessões, então a razão varia só pelo movimento.

| par | tokyo | london | london_ny_overlap | ny | other | melhor sessão (razão) |
|---|---|---|---|---|---|---|
| USDJPY | 7.2 (0.18) | 8.4 (0.15) | 9.0 (0.14) | 5.1 (0.25) | 8.2 (0.16) | london_ny_overlap |
| GBPUSD | 7.0 (0.22) | 10.5 (0.14) | 10.9 (0.14) | 6.1 (0.25) | 5.5 (0.27) | london_ny_overlap |
| AUDJPY | 11.0 (0.18) | 10.2 (0.20) | 11.9 (0.17) | 7.5 (0.26) | 11.6 (0.17) | london_ny_overlap |
| EURUSD | 5.7 (0.24) | 8.4 (0.17) | 9.3 (0.15) | 5.2 (0.27) | 4.6 (0.30) | london_ny_overlap |
| CADJPY | 8.3 (0.24) | 9.6 (0.20) | 11.6 (0.17) | 6.9 (0.29) | 9.0 (0.22) | london_ny_overlap |
| EURJPY | 7.8 (0.23) | 8.9 (0.20) | 9.2 (0.19) | 5.0 (0.36) | 7.7 (0.23) | london_ny_overlap |
| GBPJPY | 8.7 (0.24) | 10.5 (0.20) | 10.6 (0.20) | 6.1 (0.35) | 8.3 (0.25) | london_ny_overlap |
| AUDUSD | 10.0 (0.25) | 10.8 (0.23) | 12.7 (0.20) | 7.8 (0.32) | 9.6 (0.26) | london_ny_overlap |
| GBPNZD | 7.7 (0.27) | 9.2 (0.22) | 8.9 (0.23) | 5.5 (0.37) | 6.8 (0.30) | london |
| EURAUD | 8.0 (0.26) | 8.4 (0.25) | 9.3 (0.23) | 5.3 (0.40) | 7.3 (0.29) | london_ny_overlap |
| GBPCAD | 5.4 (0.35) | 9.1 (0.21) | 9.7 (0.20) | 5.2 (0.37) | 3.9 (0.49) | london_ny_overlap |
| EURNZD | 7.9 (0.28) | 8.7 (0.25) | 8.9 (0.25) | 5.6 (0.39) | 7.3 (0.30) | london_ny_overlap |
| GBPAUD | 7.9 (0.28) | 8.9 (0.25) | 9.1 (0.25) | 5.1 (0.43) | 6.7 (0.33) | london_ny_overlap |
| EURCAD | 4.9 (0.38) | 7.8 (0.24) | 9.3 (0.20) | 5.0 (0.38) | 3.9 (0.48) | london_ny_overlap |
| CHFJPY | 7.1 (0.31) | 8.4 (0.26) | 8.5 (0.26) | 4.7 (0.47) | 6.9 (0.32) | london_ny_overlap |
| USDCAD | 5.2 (0.39) | 7.2 (0.28) | 9.6 (0.21) | 6.0 (0.34) | 4.6 (0.44) | london_ny_overlap |
| NZDJPY | 10.6 (0.29) | 10.2 (0.31) | 11.3 (0.28) | 7.6 (0.41) | 11.3 (0.28) | london_ny_overlap |
| AUDCHF | 9.2 (0.34) | 9.5 (0.32) | 10.4 (0.30) | 6.3 (0.49) | 8.2 (0.38) | london_ny_overlap |
| GBPCHF | 6.3 (0.43) | 9.4 (0.29) | 9.1 (0.30) | 4.9 (0.56) | 4.3 (0.64) | london |
| CADCHF | 5.9 (0.46) | 8.9 (0.31) | 10.2 (0.27) | 5.7 (0.47) | 4.6 (0.59) | london_ny_overlap |
| USDCHF | 5.9 (0.54) | 8.9 (0.35) | 9.7 (0.33) | 5.3 (0.60) | 4.7 (0.67) | london_ny_overlap |
| NZDUSD | 9.8 (0.50) | 11.2 (0.44) | 12.5 (0.39) | 8.0 (0.61) | 9.7 (0.51) | london_ny_overlap |
| AUDCAD | 6.8 (0.53) | 7.7 (0.47) | 9.1 (0.40) | 5.2 (0.70) | 6.5 (0.56) | london_ny_overlap |
| EURGBP | 5.0 (0.61) | 8.0 (0.38) | 7.5 (0.40) | 3.8 (0.79) | 3.2 (0.94) | london |
| NZDCAD | 7.0 (0.64) | 8.5 (0.53) | 9.3 (0.48) | 5.7 (0.78) | 6.8 (0.66) | london_ny_overlap |
| AUDNZD | 5.3 (0.55) | 5.0 (0.58) | 5.1 (0.57) | 3.6 (0.82) | 5.3 (0.54) | other |
| NZDCHF | 8.9 (0.67) | 9.7 (0.62) | 10.0 (0.60) | 6.5 (0.92) | 8.1 (0.74) | london_ny_overlap |
| EURCHF | 4.3 (0.78) | 6.3 (0.54) | 6.4 (0.53) | 3.4 (1.01) | 2.9 (1.18) | london_ny_overlap |

## Movimento médio de 1h por hora UTC de entrada (28 pares)

| hora UTC | mov. 1h (bps) |
|---|---|
| 00 | 7.60 |
| 01 | 7.18 |
| 02 | 5.88 |
| 03 | 5.27 |
| 04 | 5.34 |
| 05 | 6.87 |
| 06 | 8.96 |
| 07 | 9.83 |
| 08 | 8.95 |
| 09 | 8.03 |
| 10 | 7.80 |
| 11 | 9.04 |
| 12 | 10.61 |
| 13 | 11.90 |
| 14 | 10.91 |
| 15 | 8.75 |
| 16 | 6.87 |
| 17 | 6.29 |
| 18 | 5.90 |
| 19 | 5.12 |
| 20 | 4.47 |
| 23 | 6.70 |

## Estabilidade da triagem no tempo

Correlação de postos entre a razão (4h) de cada ano e a do período inteiro — alta = a ordem dos pares é estável, não efeito de um regime.

| ano | correlação de postos |
|---|---|
| 2020 | 0.97 |
| 2021 | 0.94 |
| 2022 | 0.99 |
| 2023 | 0.98 |
| 2024 | 0.93 |
