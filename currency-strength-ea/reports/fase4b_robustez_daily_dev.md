# Fase 4b — robustez da reversão na janela `daily` (só desenvolvimento, exploratório)

Retorno em 24h **na direção do sinal** (negativo = reversão), bruto, em bps; t por cluster de dia. Hipótese formada nestes mesmos dados → só o OOS intocado pode confirmar; isto só mede fragilidade.

## daily_k5 (n=418)

- Todos: média **-34.2 bps** (t -2.42), mediana -23.5 bps, % eventos com reversão: 64%
- Aparada 5%/95%: média -29.7 bps
- Sem março/2020: média -23.1 bps (t -1.86, n=374)
- 1ª metade do dev (2022-05-15 fim): média -29.1 bps (t -1.71, n=258)
- 2ª metade do dev (2024-09-19 fim): média -42.3 bps (t -1.72, n=160)
- Por ano (bps): 2020: -56 (n=136), 2021: +5 (n=87), 2022: -32 (n=58), 2023: -20 (n=39), 2024: -47 (n=98)
- Leave-one-pair-out: média varia de -42.7 a -31.5 bps (a que mais enfraquece: sem AUDUSD → -31.5)
- Pares com mais eventos: AUDJPY 34%, NZDJPY 16%, AUDCHF 10%

## daily_k6 (n=154)

- Todos: média **-45.1 bps** (t -2.49), mediana -34.2 bps, % eventos com reversão: 68%
- Aparada 5%/95%: média -41.1 bps
- Sem março/2020: média -39.5 bps (t -2.10, n=142)
- 1ª metade do dev (2022-05-15 fim): média -34.5 bps (t -1.95, n=74)
- 2ª metade do dev (2024-09-19 fim): média -54.8 bps (t -1.81, n=80)
- Por ano (bps): 2020: -50 (n=51), 2021: +18 (n=11), 2022: -25 (n=21), 2023: -16 (n=17), 2024: -70 (n=54)
- Leave-one-pair-out: média varia de -47.8 a -42.8 bps (a que mais enfraquece: sem AUDCHF → -42.8)
- Pares com mais eventos: AUDJPY 42%, NZDJPY 22%, AUDUSD 12%
