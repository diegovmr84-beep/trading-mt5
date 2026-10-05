# Relatório — Fase 3: geração de sinais e regras de entrada/saída

**Status (2026-10-05): lógica de geração de sinais implementada, parametrizada e rodada sobre o
histórico completo (3 janelas × k = 5/6/7 → 7.207 eventos candidatos). Nenhum P&L foi calculado
e nenhum resultado do período de validação foi aberto — isso é Fase 4.**

## O que foi implementado

| Módulo | Função |
|---|---|
| `src/signals.py` | z-score par-a-par, contagem de dominância por moeda, eventos de *onset* de sinal |
| `src/calibration.py` | calibração empírica de stop/take (**só desenvolvimento**, com guarda e embargo) |
| `src/spread_model.py` | tabela de spread por (par, sessão) e filtro de pares operáveis |
| `src/split.py` | corte 70/30 único (`2024-09-24 13:44 UTC`) |
| `src/loaders.py` | carga OHLC M5 |
| `scripts/generate_signals.py` | orquestra tudo e grava `signal_candidates` / `stop_take_calibration` |

17 testes novos (58 no total, todos passando): anti-lookahead do z-score, fórmula conferida na
mão, gaps, dominância, onset, short/long, prioridade, excursões MFE/MAE, guarda de vazamento,
embargo, filtro de spread.

## Decisões de projeto (cada uma precisa da sua revisão — o estudo deixa em aberto)

### 1. "Significativo" = z-score contra a volatilidade recente (exigência explícita do item 1)

Para um par (X base / Y cotada) em T:

```
z(T) = r(T) / ( sigma1(T) · sqrt(n(T)) )      "X significativamente mais forte que Y" se z > z_crit
```

- `r(T)`: retorno **log** acumulado desde a abertura da janela (as mesmas 3 variantes da Fase 2),
  só com fechamentos até T-1. Log para a antissimetria ser exata (z de Y×X = −z de X×Y).
- `sigma1(T)`: desvio-padrão dos retornos por candle do próprio par nas últimas 2.880 observações
  (~10 dias úteis), só até T-1.
- `n(T)`: passos entre o preço-base e o preço atual; `sigma1·√n` é o desvio de um passeio
  aleatório nessa distância.

**É uma régua padronizada, não um p-value** (retornos têm cauda gorda e volatilidade que agrupa).
A inferência de verdade é no nível da estratégia (Fase 4). Cada uma dessas comparações conta no
Bonferroni (até 7 por moeda candidata), além da varredura de parâmetros — a contagem total precisa
entrar explicitamente no relatório da Fase 4.

**Critério de entrada**: a moeda forte vence com significância ≥ `k_min` das outras 7, a fraca
perde para ≥ `k_min`, **e o próprio par forte×fraca também tem |z| > z_crit**
(`require_pair_significance`, default ligado — o estudo não exige isso explicitamente; é minha
leitura de que o par negociado precisa ter o sinal, não só a moeda no agregado).

### 2. Gaps (fim de semana, feriado) encerram o segmento de acumulação
Intervalo > 2h entre candles de um par: retornos que atravessam o gap saem da estimativa de
`sigma1` e de `r(T)`, e o acúmulo recomeça no primeiro candle depois do gap. Sem isso, o "retorno
desde a abertura da janela" de uma segunda de manhã incluiria o gap do fim de semana inteiro
(`overlap` carregaria o gap de sexta 13h até segunda). É a recomendação que registrei na revisão
da Fase 1 (tratar feriado como fim de semana), agora implementada e testada.

### 3. Onset, não persistência
Um sinal que dura 50 candles gera **1 evento** (a transição "sem sinal → ativo", ou mudança de
direção), não 50 — senão a mesma oportunidade seria contada dezenas de vezes. Entrada assumida na
abertura do candle T (a decisão só usa dados até o fechamento de T-1).

### 4. Ordem dos candidatos
`priority` = posição entre os candidatos simultâneos, por diferença de força do Método A
(`força[forte] − força[fraca]`, decrescente). É a lista que a Seção 5 manda percorrer aplicando o
filtro de spread de cima para baixo. Os ranks do Método C ficam gravados ao lado (não ordenam).

### 5. Stop/take calibrados só em desenvolvimento, em unidades de volatilidade
Para cada evento, mede-se nos 36 candles seguintes (3h) a excursão favorável máxima (MFE) e
adversa máxima (MAE), normalizadas por `sigma1·√36`. Por faixa de intensidade (|z_pair|, 4
quantis **dos eventos de dev**): `take = quantil q_take do MFE`, `stop = quantil q_stop do MAE`.
As mesmas bordas e tabela são aplicadas depois, sem reajuste, aos eventos de validação.

- **Guarda programática**: `calibrate_stop_take` levanta `ValidationLeakError` se receber evento
  em/após o corte — não confia em quem chama ter filtrado certo.
- **Embargo (purga)**: eventos cuja janela de resultado cruza o corte (< 6h antes dele) ficam
  fora da calibração **e** da validação (`period='embargo'`). Sem isso, a janela de MFE/MAE de um
  evento de dev nas últimas horas leria preço de validação. Nesta rodada: 0 eventos em embargo.
- Nenhuma estatística de resultado (MFE/MAE/retorno) foi calculada para eventos de validação.

Calibração obtida, k=5 (unidades de `sigma1·√36`; só dev; **não é resultado de estratégia**):

| janela | faixa \|z\| | take | stop | n |
|---|---|---|---|---|
| daily | <3,52 / 3,52-4,04 / 4,04-4,68 / >4,68 | 0,82 / 0,76 / 0,99 / 1,08 | 1,64 / 1,62 / 1,95 / 3,26 | 141 cada |
| session | <3,78 / 3,78-4,41 / 4,41-5,34 / >5,34 | 0,81 / 0,83 / 0,90 / 1,26 | 1,41 / 1,53 / 1,71 / 1,87 | 475 cada |
| overlap | <3,71 / 3,71-4,32 / 4,32-5,22 / >5,22 | 0,85 / 0,92 / 0,90 / 1,26 | 1,49 / 1,57 / 1,81 / 1,76 | 325 cada |

**Atenção:** com os quantis-padrão (`q_take=0,5`, `q_stop=0,75`) o stop sai maior que o take
(relação risco:retorno < 1). Isso é consequência dos defaults escolhidos antes de ver o dado, não
uma conclusão — `q_take`, `q_stop`, horizonte e nº de faixas são varridos na Fase 4. Também
observa-se que o MAE no quantil 0,75 supera o de um passeio aleatório (~1,15): a volatilidade
logo após um movimento grande é maior que a média recente — esperado, e vale ter em mente.

### 6. Filtro de spread: spread relativo ≤ fração da distância do take
`spread_rel(par, sessão) ≤ 0,25 · take_rel`, com `spread_rel` = quantil 0,75 do
`(ask−bid)/mid` amostrado na Fase 1 por (par, sessão). Par/sessão sem amostra → reprova
(sem dado de custo, não assume viabilidade). Modelado dentro da geração do sinal, não só como
filtro de execução (Seção 5).

- **Morde onde a Seção 5 previu, mas pouco**: considerando todos os 7.207 eventos, os pares que
  mais reprovam são `GBPNZD` (79% reprovados, só 24 eventos) e `AUDNZD` (16%, 25 eventos) —
  spread alto frente ao movimento esperado de pares de baixa volatilidade —, seguidos de
  `CHFJPY` e `AUDJPY` (~6%), `NZDCHF`/`GBPJPY` (~3%). Os demais passam quase sempre. Os pares
  problemáticos têm poucos eventos, então o efeito agregado é pequeno.
- **É fraco nos defaults** (~98% dos eventos passam): numa janela de 3h o movimento esperado é
  muito maior que o spread da maioria dos pares. `max_spread_to_take` e o quantil do spread são os
  parâmetros que a Fase 4 varre nos 3 cenários de custo.
- **Limitação assumida**: spread amostrado só em set-out/2026, aplicado a todo o histórico
  2020-2026. Subestima o custo em regimes de stress. Além disso, esse spread de 2026 cai todo no
  período de **validação** do split; spread não depende do resultado da estratégia (não vaza
  edge), mas é uma exceção ao "validação nunca é vista" — registrada aqui por transparência.

## Resultado: eventos candidatos (apenas contagens — nenhum resultado de trade)

Parâmetros: `z_crit = 2,0`, horizonte 36, `q_take = 0,5`, `q_stop = 0,75`, quantil de spread 0,75,
`max_spread_to_take = 0,25`. Corte dev/validação: 2024-09-24 13:44 UTC.

| janela | k | eventos | dev | val | passam no spread | simultâneos (méd / máx) |
|---|---|---|---|---|---|---|
| daily | 5 | 843 | 568 | 275 | 98% | 1,36 / 7 |
| daily | 6 | 300 | 197 | 103 | 98% | 1,23 / 4 |
| daily | 7 | 51 | 38 | 13 | 100% | 1,00 / 1 |
| session | 5 | 2.696 | 1.927 | 769 | 98% | 1,44 / 9 |
| session | 6 | 797 | 570 | 227 | 99% | 1,27 / 4 |
| session | 7 | 126 | 86 | 40 | 100% | 1,00 / 1 |
| overlap | 5 | 1.814 | 1.325 | 489 | 98% | 1,42 / 7 |
| overlap | 6 | 507 | 361 | 146 | 100% | 1,27 / 4 |
| overlap | 7 | 73 | 44 | 29 | 100% | 1,00 / 1 |

O número de posições simultâneas é dinâmico (resultado do filtro, não fixado), como a Seção 5
pede: de 0 a 9 candidatos por instante.

## Limitações e riscos para a Fase 4

- **Amostras pequenas em k=7** (13 a 86 eventos de dev por janela): qualquer resultado nesses
  recortes tem que sair rotulado "preliminar" pelo critério de tamanho mínimo da Fase 4.
- **Eventos não são independentes**: candidatos simultâneos compartilham moedas (um forte contra
  vários fracos gera vários pares correlacionados). O controle por cluster de moeda (Fase 4,
  item 7) é obrigatório antes de qualquer afirmação de significância.
- **Heterocedasticidade intradiária**: `sigma1` é uma média móvel sem ajuste por hora do dia. Na
  janela `overlap`, 70% dos eventos caem na sessão `london_ny_overlap` — compatível com
  divulgações de dados dos EUA (12:30-14:00 UTC) inflando o z contra uma volatilidade média.
  Normalizar por volatilidade da mesma hora do dia é uma melhoria possível, mas adiciona
  parâmetros; não implementei sem a sua decisão.
- **`z_crit` e `k_min` não foram otimizados** — defaults neutros; a varredura e a correção de
  Bonferroni são da Fase 4.
- **Assimetria long/short** (ex.: 1.076 shorts × 738 longs em overlap k=5) reflete a convenção
  base/quote e os regimes de moeda do período, não um viés do código; não foi investigada.

## Decisões que preciso de você antes da Fase 4

- [ ] Definição de "significativo" (z contra volatilidade recente, `z_crit` varrido) está ok, ou
      prefere outro teste?
- [ ] `require_pair_significance` ligado (o par negociado também precisa de |z| > z_crit) — mantém?
- [ ] Normalizar `sigma1` por hora do dia (corrige a heterocedasticidade acima, +parâmetros) —
      vale fazer agora ou deixar como achado para a Fase 4?
- [ ] Spread medido só em 2026 e aplicado a todo o histórico: aceita essa aproximação para o
      backtest (com os 3 cenários de custo), sabendo que ela subestima custo em regimes de stress?
- [ ] Horizonte de 3h (36 candles) para a calibração stop/take — ponto de partida aceitável?
