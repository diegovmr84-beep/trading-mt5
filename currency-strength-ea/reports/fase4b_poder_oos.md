# Fase 4b — poder do teste pré-registrado no OOS (bootstrap só com desenvolvimento)

Tamanho esperado do OOS: ~257 trades (daily_k5, cenário realista). Média líquida de desenvolvimento: +18.3 bps. 1000 reamostras por dia.

| mundo simulado | média líquida verdadeira | p unilateral < 0,05 | validado | preliminar | não validado |
|---|---|---|---|---|---|
| efeito igual ao do desenvolvimento | +18.3 bps | 20% | 20% | 62% | 18% |
| metade do efeito | +9.2 bps | 7% | 7% | 61% | 32% |
| efeito zero (falso positivo) | +0.0 bps | 1% | 1% | 45% | 53% |

Leitura: mesmo que o efeito seja **exatamente** o visto no desenvolvimento (cenário otimista para a hipótese, já que ela foi escolhida entre 72 células), a chance de o teste pré-registrado validá-la é a primeira linha, coluna "validado". Com metade do efeito (o mais provável, pela maldição do vencedor), é ainda menor.