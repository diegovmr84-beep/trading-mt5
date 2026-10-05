# Relatório — Fase 2: Cálculo do índice de força

**Status: implementado e rodado sobre o histórico completo (2020-01-01 → 2026-10-02, 505.602
timestamps M5). Método A, Método C e as 3 variantes de janela todos calculados e gravados.
Nenhuma escolha de variante nem validação estatística foi feita aqui — isso é Fase 4.**

## O que foi implementado

- `src/windows.py` — as 3 variantes candidatas de janela de cálculo do retorno (Seção 3.2 do
  estudo), como parâmetro, não hardcoded:
  - `daily`: reseta às 00:00 UTC (dia corrido)
  - `session`: reseta às 00:00 / 08:00 / 13:00 UTC (aberturas de Tóquio/Londres/NY)
  - `overlap`: reseta às 13:00 UTC (abertura do overlap Londres/NY)
- `src/force_index.py` — o cálculo em si (Seção 3.0/3.1):
  - **Método A** (v1, decidido): para cada moeda, média aritmética simples dos retornos
    sinalizados dos 7 pares cruzados que a envolvem (retorno acumulado desde a abertura da
    janela). Dá magnitude.
  - **Método C** (robustez): mesmos retornos sinalizados, mas cada confronto par-a-par vira só
    +1 (ganhou) ou -1 (perdeu); soma o placar dos 7 confrontos e ranqueia por ele. Por usar sinal
    em vez de magnitude, um par com movimento gigante não domina o resultado como pode dominar a
    média do Método A — é a robustez a outlier que a Seção 3.1 pede dessa variante.
  - **Anti-lookahead por construção** (Seção 3.2): o retorno atribuído ao candle T usa só preços
    conhecidos até o fechamento de T-1 (`close.shift(1)`, tanto como "preço atual" quanto para
    fixar o preço-base da janela). Não é um filtro aplicado depois — é a própria fórmula. Testado
    explicitamente: mudar o close de um candle não muda nenhum retorno calculado até e incluindo
    aquele candle, só os seguintes (`tests/test_force_index.py`).
- `scripts/compute_force_index.py` — roda os dois métodos nas 3 variantes sobre os 28 pares
  (Fase 1) e grava em `force_index(ts_utc, variant, currency, force_a, rank_c)`.
- `scripts/force_index_report.py` — relatório de concordância/divergência entre A e C
  (`reports/force_index_a_vs_c.md`, item 6 da Fase 2).
- 15 testes novos (`test_windows.py`, `test_force_index.py`, + 2 em `test_db.py`), 41 no total,
  todos passando. Cobrem: cada variante de janela, anti-lookahead, decomposição base/cotada com
  sinais corretos (conferida na mão), e um caso construído onde A e C **divergem de propósito**
  (outlier dominando a média de A) — prova de que o Método C não é só A reformatado.

## Números reais (rodado em 2026-10-05)

12.132.747 linhas em `force_index` (505.594-505.602 timestamps × 8 moedas × 3 variantes, menos
timestamps de borda sem 3+ moedas comparáveis). `force_a` médio por moeda fica em ~0 (esperado —
é retorno acumulado desde a abertura da janela, reseta todo dia); faixa observada de -4,1% a
+4,7% nos casos mais extremos de um dia inteiro, plausível pra M5 ao longo de 6,7 anos.

### Bug encontrado e corrigido rodando contra dado real

A primeira execução gravou só 24 linhas em vez de ~12 milhões — todos os timestamps colapsaram
no mesmo valor de epoch por causa de `.astype("int64") // 10**9` presumindo nanossegundos; o
pandas 3.0 preserva a resolução de origem do `DatetimeIndex` (aqui veio em segundos, de
`pd.to_datetime(..., unit="s")`), então a divisão por 10⁹ zerava o timestamp. Corrigido com
`.as_unit("s")` antes do `astype` (robusto a qualquer resolução de origem), com dois testes de
regressão adicionados (`test_force_index_to_rows_epoch_correto_em_qualquer_resolucao_do_indice`).
Sem esse teste, o bug não teria aparecido nos testes unitários (que usavam índices sintéticos com
outra resolução) — só apareceu rodando contra o dado real, por isso está documentado aqui.

## Método A vs. Método C — concordância/divergência (ver relatório completo)

Resumo de `reports/force_index_a_vs_c.md` (gitignored no detalhe por par/dia, mas o sumário por
variante fica aqui):

| variante | ρ médio | timestamps com concordância total | divergência grande (ρ<0,5) | moeda mais forte: A e C concordam |
|---|---|---|---|---|
| daily   | 0,9961 | 89,1% | 0,0% (38 timestamps) | 98,5% |
| session | 0,9956 | 86,3% | 0,0% (24 timestamps) | 98,3% |
| overlap | 0,9947 | 85,3% | 0,0% (14 timestamps) | 97,9% |

**Concordância muito alta nas três variantes** — divergência grande é rara (dezenas de timestamps
em meio a meio milhão). Não decido aqui se isso valida ou não o Método A; registro para revisão,
conforme a Fase 2 pede. A moeda com maior divergência média de ranking entre os métodos é CHF em
todas as variantes (ainda assim pequena: ~0,04-0,06 posições de rank em média).

## O que NÃO foi feito nesta fase (de propósito)

- **Nenhuma das 3 variantes de janela foi escolhida** — isso é Fase 4, com base no período de
  desenvolvimento (70%).
- **Mínimos quadrados não implementado** — explicitamente adiado pela Seção 3.1, condicional ao
  resultado da validação estatística da Fase 4.
- **Nenhum filtro de spread aplicado ao cálculo** — o índice usa os 28 pares completos, spread
  entra só na seleção de pares operáveis (Fase 3), por decisão explícita da Seção 3.3.
- **Nenhum sinal de entrada/trade gerado** — isso é Fase 3.

## Limitações / decisões que precisam da sua revisão

- [x] Fórmula do Método C (placar de vitórias/derrotas via sinal, não magnitude) é minha
      interpretação de "mesmo cálculo de base, convertido em ranking ordinal" (Seção 3.1).
      **Decidido pelo usuário em 2026-10-05: Leitura 1 (placar de sinais), mantida.** A
      alternativa (ordenar as magnitudes do A) deixaria A e C idênticos por construção.
- [ ] Linhas onde uma moeda não tem nenhum par disponível (feriado afetando parcialmente o
      universo) ficam com `force_a`/`rank_c` nulos para aquela moeda naquele timestamp — revisar se
      a Fase 3/4 deve tratar isso como "sem sinal" ou exigir as 8 moedas completas.
- [ ] Buracos de feriado (já sinalizados na Fase 1, `data_gaps`) ainda não são tratados
      especificamente aqui — o primeiro candle após um feriado longo calcula retorno normalmente
      contra a janela aberta antes do feriado, o que pode gerar um valor de força artificialmente
      grande nesse candle específico. Fica para quem for usar a série (Fase 3/4) filtrar essas
      bordas usando `data_gaps`.
