# Fase 4b — perfil descritivo da v2 no desenvolvimento (NÃO é evidência)

Fade de sinais `daily`, entrada na abertura, saída por tempo em 24h, sem stop. **A hipótese foi formada nestes mesmos dados (escolhida entre 72 células), então estes números são otimistas por construção** — só o out-of-sample intocado pode confirmar. O que este perfil acrescenta de verdade é o **risco**: a pior excursão adversa (MAE) de segurar 24h sem proteção.

## daily_k5 (568 eventos de desenvolvimento)

| cenário | n | bruto (bps) | líquido (bps) | mediana líq. (bps) | t | hit rate | MAE mediano / p95 / máx (bps) |
|---|---|---|---|---|---|---|---|
| otimista | 531 | +21.1 | +19.7 | +13.2 | +1.42 | 59% | 52 / 193 / 588 |
| realista | 531 | +21.1 | +18.3 | +10.9 | +1.33 | 58% | 52 / 193 / 588 |
| pessimista | 531 | +21.1 | +16.3 | +8.6 | +1.18 | 55% | 52 / 193 / 588 |

Concentração (realista): par mais frequente **AUDJPY** = 34% dos trades; média líquida sem ele +25.0 bps; 1ª metade +7.9, 2ª metade +38.3 bps.

## daily_k6 (197 eventos de desenvolvimento)

| cenário | n | bruto (bps) | líquido (bps) | mediana líq. (bps) | t | hit rate | MAE mediano / p95 / máx (bps) |
|---|---|---|---|---|---|---|---|
| otimista | 192 | +35.8 | +34.5 | +25.0 | +2.07 | 65% | 54 / 205 / 588 |
| realista | 192 | +35.8 | +33.2 | +23.7 | +2.00 | 64% | 54 / 205 / 588 |
| pessimista | 192 | +35.8 | +31.3 | +21.8 | +1.89 | 62% | 54 / 205 / 588 |

Concentração (realista): par mais frequente **AUDJPY** = 45% dos trades; média líquida sem ele +38.0 bps; 1ª metade +18.0, 2ª metade +47.8 bps.
