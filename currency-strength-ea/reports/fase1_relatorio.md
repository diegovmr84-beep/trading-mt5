# Relatório — Fase 1: Coleta de dados e levantamento de spread

**Status: histórico M5 dos 8 majors 2020→2026 COMPLETO e verificado (3.998.288 candles).
Amostragem de spread ao vivo EM ANDAMENTO (iniciada 2026-09-03, ~460 mil amostras).
Os 20 pares cruzados não-major ainda não têm histórico (majors-first, decisão de escopo).**

## 1. Histórico de candles M5 — Dukascopy (COMPLETO para os 8 majors)

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

## 2. Spread real por par/sessão — MT5/Exness ao vivo (EM ANDAMENTO)

`scripts/spread_sampler.py`, rodando contra o terminal MT5 da conta **Exness-MT5Trial11** (demo),
sufixo de símbolo `m`. Amostra bid/ask dos 28 pares a cada 30s, taggeado por sessão.

- **Início**: 2026-09-03 20:48 UTC. **Amostras até 2026-09-10 ~04:00**: ~460 mil, cobrindo as 5
  categorias de sessão (tokyo/london/ny/london_ny_overlap/other).
- **Meta**: 2-3 semanas corridas para ter volume suficiente em cada sessão, incl. segunda pós-gap.
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
- [x] Histórico M5 dos 8 majors: completo e verificado (esta revisão).
- [ ] **20 pares cruzados não-major sem histórico** — decisão de escopo (majors-first). Definir se
      e quando baixar o resto (mesmo script, `--pairs <lista>`), ~2 dias a mais de download.
- [ ] **Spread da conta Trial precisa ser revalidado numa conta real antes da Fase 5** — demo às
      vezes simula spread mais favorável. Coleta na Trial serve pra calibração inicial, marcada
      como pendente de revalidação.
- [ ] Confirmar se 2-3 semanas de amostragem de spread é aceitável.
- [ ] Preço **mid** (não bid) nos candles Dukascopy — revisar a justificativa (README, Seção 3.3).
- [ ] Convenção base/quote dos 28 pares (`EUR > GBP > AUD > NZD > USD > CAD > CHF > JPY`).
- [ ] Buracos de feriado (Natal ~14h, Réveillon ~24h) na série M5 — Fase 2 precisa tratá-los ao
      construir retornos; não são erro de coleta.

## 7. Pergunta em aberto do próprio estudo (Seção 10)

- [ ] Limites de spread por par na Exness para o filtro de pares operáveis — depende do
      `spread_report` quando a amostragem tiver volume suficiente.
