# Relatório — Fase 4: backtest e validação estatística

## Veredicto: **NÃO VALIDADO**

- expectativa líquida no desenvolvimento <= 0 (-0.98 bps) — sem edge in-sample

Corte desenvolvimento/validação: **2024-09-24T13:44 UTC** (70/30). **A validação (out-of-sample) NÃO foi aberta.** Regras de decisão pré-registradas em `src/backtest_config.py` (commit anterior a qualquer resultado).

## 1. Pré-registração (fixada antes de rodar)

- Grade: 3 janelas × k = 5/6/7 = 9 configurações; demais parâmetros nos defaults aprovados da Fase 3.
- Cenários de custo (aprovados): otimista 1× o spread medido, realista 2×, pessimista 3× + 0,5 spread de slippage. O cenário **realista** manda na seleção e no veredicto; os outros são sensibilidade.
- **Contagem de Bonferroni: 63 = 9 configurações × 7 comparações par-a-par internas por moeda candidata** → α crítico = 0.05/63 = 0.00079. As duas camadas (varredura de parâmetros e testes internos do critério de entrada) entram na contagem, como o estudo exige. Contagem conservadora e minha interpretação: a camada interna é um fator multiplicativo fixo de 7.
- Amostra mínima: 100 trades (abaixo disso: **preliminar**). Efeito mínimo: expectativa líquida ≥ 0.1 R (R = stop médio). Ambos [SUPOSIÇÃO], análogos ao |r| > 0,3 do outro projeto.
- Significância: erro-padrão **robusto a cluster por dia UTC** (trades do mesmo dia compartilham choques e moedas; tratá-los como independentes inflaria a significância).
- Simulação: entrada na abertura do candle do sinal; stop e take nos níveis calibrados só no desenvolvimento; stop e take no mesmo candle → assume stop; saída por tempo em 36 candles; sem posição carregada por gap.

## 2. Varredura no desenvolvimento (9 configurações × 3 cenários de custo)

Expectativa líquida por trade em bps (retorno log × 10⁴), t robusto a cluster, expectativa em R. `prel.` = menos de 100 trades.

| config | n (realista) | otimista (bps) | **realista (bps)** | pessimista (bps) | t realista | R realista | sig. Bonferroni? |
|---|---|---|---|---|---|---|---|
| daily_k5 | 492 | -3.88 | **-4.77** | -6.56 | -2.49 | -0.088 | não |
| daily_k6 | 184 | -4.73 | **-6.54** | -7.10 | -1.71 | -0.122 | não |
| daily_k7 | 37 prel. | -7.64 | **-8.75** | -9.98 | -1.18 | -0.124 | não |
| session_k5 | 1724 | -0.80 | **-1.84** | -2.80 | -1.54 | -0.047 | não |
| session_k6 | 533 | 0.08 | **-0.98** | -2.35 | -0.65 | -0.021 | não |
| session_k7 | 83 prel. | -5.17 | **-6.11** | -7.81 | -1.11 | -0.085 | não |
| overlap_k5 | 1192 | -0.82 | **-1.87** | -3.03 | -0.96 | -0.047 | não |
| overlap_k6 | 329 | -3.13 | **-4.15** | -5.52 | -1.48 | -0.077 | não |
| overlap_k7 | 42 prel. | -3.20 | **-4.95** | -7.40 | -0.59 | -0.063 | não |

**Nenhuma das 9 configurações tem expectativa líquida positiva e significativa no cenário realista.** Única com média positiva em algum cenário: `session_k6` no otimista (+0,08 bps, indistinguível de zero).

### Por que é negativo: bruto ≈ 0, e o custo empurra para baixo

Diagnóstico só com o desenvolvimento (cenário realista, as 9 configurações): o retorno **bruto** (antes de custo) fica entre −6,5 e +1,6 bps por trade conforme a configuração, ou seja, o sinal **não mostra edge antes de custo**; o custo (1,3 bps no otimista, ~2,5 no realista) só faz o resultado cruzar para o negativo. Take atingido em ~48% dos trades, stop em ~20%, saída por tempo em ~31%. A relação stop/take média é 1,8 — efeito dos quantis-padrão (q_take 0,5 / q_stop 0,75) definidos antes de ver o dado.

## 3. Configuração escolhida (regra pré-registrada) e walk-forward

Regra: maior t entre as configurações com ≥ 100 trades, cenário realista. Escolhida: **session_k6** — n=533, líquido -0.98 bps, t=-0.65, p=0.520, -0.021 R. É a "menos ruim", não uma configuração com edge.

**Walk-forward** (treina 6 meses, testa 1, recalibra stop/take e reescolhe a configuração a cada dobra, só dentro do desenvolvimento): 50 dobras, 46 com trades; 529 trades de teste; média líquida **-1.06 bps** (t=-0.62); 46% dos meses positivos. Sem estabilidade de edge ao longo do tempo — consistente com ausência de edge.

## 4. Concentração por faixa de spread (item 10 — descritivo, NÃO usar para escolher pares)

| faixa de custo | trades (9 configs somadas) | bruto (bps) | líquido (bps) |
|---|---|---|---|
| A | 2961 | -0.49 | -2.50 |
| B | 1150 | -1.99 | -4.88 |
| C | 505 | 7.04 | 2.28 |

A faixa C (maior custo relativo) é a única com média positiva. **Isso não é acionável**: é um subgrupo pós-hoc, os trades das 9 configurações se sobrepõem (não são independentes), não há correção de múltiplos testes e as diferenças por par ficam dentro do ruído (±10 bps com 60-500 trades). Serve, no máximo, como **hipótese a pré-registrar** e testar uma única vez no out-of-sample ainda intocado.

## 5. Item 10 — mínimos quadrados

**Não implementado**, conforme o estudo. Recomendação documentada: o problema aqui é ausência de edge bruto na média, e não ruído concentrado em pares de spread alto/liquidez baixa (a faixa C não é pior que as outras; é a única melhor). Trocar a média simples por mínimos quadrados tende a mudar pouco um sinal cujo retorno bruto já é ≈ 0. Não recomendo gastar essa iteração agora; fica registrado para decisão sua.

## 6. Validação (out-of-sample)

**Não aberta.** Pela regra pré-registrada, "não validado" não exige o OOS: a expectativa líquida da melhor configuração já é ≤ 0 no desenvolvimento. Abrir o OOS aqui só queimaria o único dado nunca visto, sem chance de validar; e qualquer redesenho feito depois de olhar o OOS passaria a ter o OOS contaminado. O trava de abertura única (`validation_lock`) continua livre.

## 7. Limitações que valem para qualquer leitura

- O spread da Trial é fixo (piso de custo); os cenários 2×/3× são suposições. Uma conta real pode custar mais.
- 1×/2×/3× e os limiares de amostra/efeito são suposições minhas, não dados; estão visíveis em `src/backtest_config.py`.
- Configurações com k=7 têm 37-83 trades de desenvolvimento: rotuladas preliminares.
- Calibração de stop/take no desenvolvimento inteiro é in-sample para o varrimento (leve otimismo); o walk-forward recalibra por dobra e confirma o mesmo quadro.
