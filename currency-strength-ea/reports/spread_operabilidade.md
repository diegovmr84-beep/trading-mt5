# Operabilidade por par — spread da Exness Trial vs. movimento esperado

Amostras de spread: 2,413,348. **32.3% foram gravadas com o mercado fechado** (sáb/dom, cotação congelada) e foram descartadas; amostras no rollover (16h-19h de NY) ficam fora do spread "normal" e são tratadas à parte.

## Achados

1. **Fora do rollover, o spread de cada par é constante ao longo do dia** (razão máx/mín entre horas, no pior par: 1.67×). Uma conta real varia entre Tóquio/Londres/NY; isto indica spread fixo/simulado da conta Trial. **Os números abaixo são um piso de custo, não uma estimativa do spread real de execução.**
2. **O spread largo que aparece no bid/ask bruto vem do rollover e do fim de semana**, não do spread normal dos pares (ver colunas de rollover).
3. 4.7% dos eventos de sinal da Fase 3 caem no rollover — nunca operáveis.

## Custo vs. movimento esperado (só período de desenvolvimento para a volatilidade)

| par | faixa | spread (pips) | spread (bps) | take típico (bps) | custo/take | rollover p95 (pips) | rollover máx (pips) |
|---|---|---|---|---|---|---|---|
| USDJPY | A | 1.0 | 0.64 | 18.5 | 0.035 | 15.8 | 35.0 |
| GBPUSD | A | 1.0 | 0.75 | 19.4 | 0.039 | 12.1 | 26.0 |
| AUDJPY | A | 1.1 | 0.99 | 24.9 | 0.040 | 10.8 | 16.8 |
| EURUSD | A | 0.8 | 0.70 | 15.8 | 0.044 | 7.0 | 13.1 |
| CADJPY | A | 1.1 | 0.99 | 20.9 | 0.047 | 7.2 | 22.7 |
| EURJPY | A | 1.6 | 0.89 | 18.5 | 0.048 | 23.0 | 24.0 |
| GBPJPY | A | 2.2 | 1.05 | 21.3 | 0.049 | 30.4 | 30.4 |
| AUDUSD | A | 0.9 | 1.26 | 23.6 | 0.054 | 6.5 | 23.2 |
| GBPNZD | A | 2.4 | 1.03 | 19.0 | 0.054 | 45.1 | 80.0 |
| EURAUD | A | 1.7 | 1.05 | 18.6 | 0.057 | 20.4 | 58.0 |
| GBPCAD | A | 1.8 | 0.96 | 16.8 | 0.057 | 12.7 | 27.5 |
| GBPAUD | A | 2.1 | 1.11 | 18.9 | 0.059 | 24.8 | 60.0 |
| EURNZD | A | 2.2 | 1.10 | 18.4 | 0.060 | 49.2 | 86.4 |
| EURCAD | B | 1.5 | 0.93 | 14.8 | 0.063 | 9.5 | 19.5 |
| CHFJPY | B | 2.1 | 1.11 | 17.5 | 0.063 | 18.1 | 50.0 |
| NZDJPY | B | 1.4 | 1.56 | 24.1 | 0.065 | 11.8 | 25.0 |
| USDCAD | B | 1.4 | 1.01 | 14.7 | 0.068 | 6.3 | 16.4 |
| AUDCHF | B | 0.9 | 1.54 | 21.3 | 0.072 | 6.4 | 31.4 |
| GBPCHF | B | 1.5 | 1.37 | 17.6 | 0.078 | 11.5 | 38.3 |
| CADCHF | B | 0.8 | 1.36 | 17.0 | 0.080 | 5.9 | 18.0 |
| USDCHF | B | 1.3 | 1.58 | 16.4 | 0.097 | 7.6 | 30.0 |
| NZDUSD | C | 1.4 | 2.44 | 23.5 | 0.104 | 8.6 | 11.6 |
| EURGBP | C | 1.3 | 1.52 | 14.5 | 0.104 | 5.7 | 14.6 |
| AUDCAD | C | 1.8 | 1.81 | 17.3 | 0.105 | 7.4 | 23.8 |
| AUDNZD | C | 1.8 | 1.45 | 12.4 | 0.117 | 8.4 | 38.4 |
| NZDCAD | C | 1.8 | 2.24 | 17.9 | 0.125 | 10.3 | 20.1 |
| EURCHF | C | 1.6 | 1.70 | 12.1 | 0.140 | 12.4 | 32.4 |
| NZDCHF | C | 1.4 | 2.97 | 21.0 | 0.142 | 7.6 | 15.1 |

Faixas: A (custo/take ≤ 0.06) = 13 pares · B (0.06-0.1) = 8 · C (> 0.1) = 7. Os pares da faixa C são os de baixa volatilidade e/ou spread relativo alto (cruzados com NZD e CHF) — o que a Seção 5 do estudo antecipou.