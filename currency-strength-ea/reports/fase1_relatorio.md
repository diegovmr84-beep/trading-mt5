# Relatório — Fase 1: Coleta de dados e levantamento de spread

**FASE 1 ENCERRADA (2026-10-04). Histórico M5 dos 28 pares 2020→2026 completo e verificado
(14.069.101 candles). Amostragem de spread ao vivo completa e PARADA — rodou 2026-09-03 a
2026-10-04 (31 dias, acima da meta de 2-3 semanas), 2.413.348 amostras, zero combinação
par/sessão com dado insuficiente (ver `reports/spread_por_par_sessao.md`, limiar 200 amostras).
Faltam só as decisões de revisão listadas na Seção 6 antes de avançar pra Fase 2.**

## 1. Histórico de candles M5 — Dukascopy (COMPLETO para os 28 pares)

Verificação de integridade nos 28 pares (2026-10-04): **0 candles com preço zero/negativo, 0 com
OHLC inconsistente**, em todo o dataset. `data_gaps`: 58 registros, todos fechamento de mercado
(Ano Novo + um Natal que caiu em fim de semana longo em 2023) — nenhum buraco de dado real.
Os 20 cruzados foram baixados em passadas sucessivas de `--resume` (cada par para sozinho numa
hora que falha após ~15min de retry, sem deixar buraco mudo, e retoma na passada seguinte — por
isso o backfill "falhou" dezenas de vezes no log: é o comportamento esperado, não erro).

### Números dos 8 majors (congelados em 2026-09; serão atualizados pelo top-up)

Fonte: tick history público da Dukascopy (`datafeed.dukascopy.com`), decodificado do formato
`.bi5` (LZMA + registros de 20 bytes) e reamostrado para M5 localmente, usando **preço mid
((ask+bid)/2)**. Ver `src/dukascopy.py` e `README.md` para a justificativa do mid.

### Números reais (verificados em 2026-09-10)

| par | período | candles | % do teórico |
|---|---|---|---|
| EURUSD | 2020-01-01 → 2026-09-04 | 499.690 | 99,6% |
| GBPUSD | 2020-01-01 → 2026-09-04 | 499.572 | 99,6% |
| USDJPY | 2020-01-01 → 2026-09-09 | 500.376 | 99,6% |
| USDCHF | 2020-01-01 → 2026-09-09 | 499.922 | 99,5% |
| USDCAD | 2020-01-01 → 2026-09-09 | 500.371 | 99,6% |
| AUDUSD | 2020-01-01 → 2026-09-04 | 499.591 | 99,6% |
| NZDUSD | 2020-01-01 → 2026-09-04 | 499.265 | 99,5% |
| EURGBP | 2020-01-01 → 2026-09-04 | 499.501 | 99,6% |
| **total** | | **3.998.288** | |

O déficit de ~0,4-0,5% vs o teórico (288 candles/dia × ~5/7 dias) é **inteiramente feriado de
mercado** — não é perda de dado. Ver checagem de integridade abaixo.

### Checagem de integridade (script ad hoc, 2026-09-10)

1. **Sanidade de preço**: 0 candles com preço zero/negativo, 0 com OHLC inconsistente
   (high<low, etc.), em todos os 8 pares. Faixas min-max coerentes com o mercado real do período
   (ex: EURUSD 0,954-1,235; GBPUSD 1,034-1,425 incluindo o flash de set/2022; USDJPY 101-164).
2. **`data_gaps`: 16 registros, todos benignos** — são o fechamento de Ano Novo (2020→2021 e
   2023→2024), ~72h cada, 2 por par. O detector (`src/gaps.py`, limiar 72h) pega esses.
3. **Feriados abaixo do limiar de 72h** (NÃO ficam em `data_gaps`, mas existem na série e são
   normais): Natal (~14h de buraco, todo 25/12) e Réveillon de dias úteis (~24h, 31/12 de 2024 e
   2025). Sistemáticos e idênticos entre pares → mercado fechado, não falha de coleta.
   **Fase 2+ deve tratar esses buracos de feriado ao construir a série de retorno.**
4. **Horas que "pararam" um par durante o backfill** (o script para o par numa hora que não
   baixa após ~15 min de retry, para não deixar buraco silencioso — ver §4): todas foram
   preenchidas nas passadas de `--resume` seguintes. Verificado: os dias
   (USDJPY 2025-08-13, USDCHF 2023-10-26, EURUSD 2020-05-05, GBPUSD 2021-08-18) têm as 24h
   completas. USDCAD 2020-10-16 e USDCHF 2021-07-23 são sextas — hora 21-23 ausente é o
   fechamento normal de sexta, não buraco.

### Campo `broker_spread` nos candles

Guardado só como referência secundária (spread médio do bucket em pontos, calculado dos ticks
Dukascopy). **NÃO é a fonte do levantamento de spread da Fase 1** — isso é exclusivo do
`spread_sampler.py` ao vivo (§2). Valores típicos observados: 1-3 pontos para EURUSD (nível
interbancário, mais apertado que varejo — esperado).

## 2. Spread real por par/sessão — MT5/Exness ao vivo (COMPLETO, parado em 2026-10-04)

`scripts/spread_sampler.py`, rodado contra o terminal MT5 da conta **Exness-MT5Trial11** (demo),
sufixo de símbolo `m`. Amostrou bid/ask dos 28 pares a cada 30s, taggeado por sessão.

- **Período**: 2026-09-03 20:48 UTC → 2026-10-04 (31 dias corridos, acima da meta de 2-3 semanas).
  **2.413.348 amostras** no total.
- **Cobertura**: `scripts.spread_report --min-samples 200` roda sobre os 28 pares × 5 sessões
  (tokyo/london/ny/london_ny_overlap/other) e **nenhuma combinação ficou como "DADO
  INSUFICIENTE"** — a mais fraca ainda tem milhares de amostras. Relatório em
  `reports/spread_por_par_sessao.md` / `.csv` (gitignored, dado real local).
- Processo parado deliberadamente após confirmar a cobertura — não dá mais ganho rodar além disso.
- **Buracos conhecidos na série de spread** (registrados por honestidade, reabsorvíveis numa
  coleta de semanas):
  - ~7,3h em 2026-09-08 (09:05→16:27 UTC): o supervisor v1 amplificou um hiccup do MT5 num
    festival de reinícios. Corrigido com backoff exponencial (supervisor v2).
  - ~7 min em 2026-09-09 (~21:43→21:50 UTC): o restart da sessão do Claude Code matou os
    processos; religados na sequência.
- Relatório agregado: `python -m scripts.spread_report --min-samples 200` (pares/sessões abaixo
  do mínimo aparecem como "DADO INSUFICIENTE", nunca com número estimado).

## 3. Linha do tempo desta fase

1. Infra escrita numa sessão remota (sem MT5/Dukascopy): 28 pares, schema SQLite, conector MT5,
   scripts de download/amostragem/relatório.
2. Sessão local Windows, terminal MT5 Exness já logado. Diagnóstico: sufixo `m` em 28/28 pares.
3. **Download via MT5 bateu em dois limites** da conta Trial (não bugs): limite de 100k barras no
   gráfico (~347 dias), e M5 só disponível a partir de ~2025 nessa conta. H1/H4/D1 têm 2020+.
4. **Decisão**: separar as fontes em vez de trocar o timeframe do estudo (trocar pra H1 criaria
   descompasso entre timeframe do índice de força e o de execução). Adotado:
   - Histórico de candles M5 2020+ → **Dukascopy** (reamostrado localmente).
   - Spread real → continua **exclusivamente MT5/Exness ao vivo** (exigência da Seção 6).
5. Implementado `src/dukascopy.py`, `download_history_dukascopy.py`, `dukascopy_smoke_test.py`,
   `src/gaps.py`. Smoke test validado em `EURUSD 2024-06-04 10:00` contra arquivo real.
6. **Backfill dos 8 majors** (2026-09-03 → 2026-09-10): rodado em background, faseado
   (majors primeiro), com várias correções feitas rodando de verdade (§4). 3.998.288 candles.
7. **Spread sampler** iniciado em paralelo 2026-09-03, segue rodando.

## 4. Correções feitas durante o backfill (todas commitadas)

Descobertas rodando contra a Dukascopy/MT5 reais, não presumidas:

- **User-Agent**: a Dukascopy devolve HTTP 429 ao UA padrão do `requests`; com UA de navegador,
  200. (`REQUEST_HEADERS` em `src/dukascopy.py`.)
- **Throttle 503**: sob rajada a Dukascopy 503-a em série (e trava conexão) e libera em ~1-2 min.
  5xx e read-timeout agora compartilham um orçamento único de ~15 min de insistência por hora;
  esgotado, o par **para com aviso** (nunca buraco silencioso) e é retomado por `--resume`.
  `--workers` 12→4 (acima disso a Dukascopy corta).
- **SQLite em WAL + busy_timeout**: backfill e sampler escrevem no mesmo arquivo em paralelo.
- **Modo "anexar ao terminal MT5 já aberto"** no `mt5_connector` (sem credenciais no ambiente).
- **`spread_sampler_supervisor.py`**: o sampler às vezes pendura numa chamada MT5 (sem erro) ou
  nem inicializa. Supervisor externo reinicia com backoff exponencial nas falhas seguidas; após
  5 falhas loga `ALERTA` (terminal precisa de atenção humana).

## 5. Estrutura de dados (SQLite, `data/currency_strength.db`, gitignored)

- `candles_m5(symbol_id, ts_utc, open, high, low, close, tick_volume, real_volume, broker_spread)`
  — PK (symbol_id, ts_utc), upsert-safe.
- `spread_samples(symbol_id, ts_utc, session, bid, ask, spread_points)` — append.
- `data_gaps(symbol_id, gap_start_utc, gap_end_utc, note)` — recalculado por par a cada run.
- `symbols(id, name, base_currency, quote_currency)` — os 28 pares canônicos.

## 6. Limitações / decisões que precisam da sua revisão

- [x] Sufixo de símbolo Exness: `m`, confirmado rodando.
- [x] Histórico M5 dos 8 majors: completo e verificado.
- [x] 20 pares cruzados: completo e verificado (28/28).
- [x] 2-3 semanas de amostragem de spread: cumprido e excedido (31 dias, cobertura completa).
- [x] **Spread da conta Trial revalidar numa conta real antes da Fase 5 — revisado, recomendação:
      manter a exigência, mas como gate no início da Fase 5/6, não bloqueando Fases 2-4.** O
      próprio estudo (linha 157 / `currency-strength-prompt.md` Fase 6) já define Fase 5/6 como
      "paper trading em conta **demo** Exness" — ou seja, nenhuma fase planejada hoje usa conta
      real de fato. Proposta: antes de abrir Fase 5, comparar a distribuição de spread da Trial
      (já coletada) contra uma amostra curta numa conta Exness real (mesmo sem capital
      significativo, só pra capturar o bid/ask de verdade) para um subconjunto de pares/sessões
      críticos. Se bater dentro de uma tolerância, segue com os limiares calibrados na Trial; se a
      demo for sistematicamente mais apertada, recalibrar os limiares de spread por par (Seção 5
      do estudo) antes de qualquer paper trading. Não é bloqueio agora — é checklist de abertura
      da Fase 5.
- [x] **Preço mid (não bid) nos candles Dukascopy — revisado, recomendação: manter.** Consistente
      com a separação que o próprio estudo exige (Seção 3.3): o índice de força usa a série de
      preço "limpa" (mid, sem metade do spread embutida no retorno), e o custo de operar entra uma
      única vez, no filtro de pares operáveis (spread ao vivo, Seção 5/6). Usar bid duplicaria o
      efeito do spread (uma vez no cálculo do índice, outra no filtro). Nota: mesmo o bid/ask da
      própria Dukascopy (pool interbancário) não seria igual ao da Exness retail de qualquer
      forma — por isso mid "broker-agnostic" pro cálculo, e Exness ao vivo pro custo real, são as
      fontes corretas e já estão corretamente separadas no código.
- [x] **Convenção base/quote `EUR > GBP > AUD > NZD > USD > CAD > CHF > JPY` — revisado,
      recomendação: manter.** Não é arbitrária: é a precedência padrão de mercado, é como o
      MT5/Exness e a Dukascopy já expõem os símbolos (confirmado baixando os 28 pares reais — ex.
      `EURGBP`, nunca `GBPEUR`), e o sinal do retorno na decomposição de força (Seção 3.0) depende
      dessa convenção ser consistente com a fonte de dado. Trocar inverteria sinais sem ganho
      nenhum e quebraria o alinhamento com os símbolos reais da corretora.
- [x] **Buracos de feriado (Natal ~14h, Réveillon ~24h) na série M5 — revisado, não é defeito de
      coleta; é o parâmetro "tratamento de gaps de feriado" que o próprio estudo (Seção 3.2) já
      lista como a ser decidido na Fase 2, não na Fase 1.** Recomendação concreta para a Fase 2:
      tratar feriado igual a fim de semana — não fabricar candle nem interpolar; ao calcular
      retorno de sessão (Seção 3.2), excluir ou marcar separadamente qualquer sessão cujo início
      caia logo após um gap registrado em `data_gaps` (mesma tabela já populada nesta fase), pra
      não confundir "liquidez voltando após feriado" com um movimento de força real.

## 7. Pergunta em aberto do próprio estudo (Seção 10)

- [ ] Limites de spread por par na Exness para o filtro de pares operáveis — depende do
      `spread_report` quando a amostragem tiver volume suficiente.
