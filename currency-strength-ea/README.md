# Currency Strength EA — Fase 1: coleta de dados e levantamento de spread

Projeto 4 do portfólio, independente do EA de índices. Ver `docs/estudo-previo-currency-strength.md`
e `docs/currency-strength-prompt.md` para o design completo e o plano de fases. Este diretório
implementa a **Fase 1**.

## Arquitetura: duas fontes de dado, propositalmente separadas

| Dado | Fonte | Por quê |
|---|---|---|
| Histórico de candles M5 (2020+, 28 pares) | **Dukascopy** (tick history público) | A conta MT5 Trial disponível só tem histórico M5 a partir de ~2025-05 (limitação da própria conta demo, não do código — ver `reports/fase1_relatorio.md`). Dukascopy é usado só para reconstruir a série de preço; não precisa ser da mesma corretora que vai executar. |
| Spread real por par/sessão | **MT5/Exness ao vivo** | Não pode vir de outra fonte — o estudo (Seção 6) exige o spread real da corretora que vai operar, não uma estimativa ou o dado de outra corretora. |

Nenhum dos dois caminhos usa número inventado como se fosse dado de mercado — isso violaria o
princípio central do estudo prévio.

## ⚠️ Limitações desta sessão

- **MT5 só roda em Windows.** O terminal precisa estar instalado e logado; os scripts que falam
  com ele (`spread_sampler.py`, `list_symbols.py`, `download_history.py`) não funcionam neste
  ambiente Linux nem em qualquer máquina sem o terminal.
- **Este ambiente também não tem acesso de rede à Dukascopy** (só um allowlist restrito de hosts).
  Por isso o download via `download_history_dukascopy.py` também não pôde ser executado nem
  validado aqui contra um arquivo real — só a lógica de decodificação foi testada com dados
  sintéticos (`tests/test_dukascopy.py`). **Rode `scripts/dukascopy_smoke_test.py` numa hora/par
  conhecido antes de disparar o download completo**, e confira visualmente que os preços saem
  plausíveis.
- Portanto: nenhum dado real (histórico ou spread) foi coletado nesta sessão. Ver
  `reports/fase1_relatorio.md` para o estado detalhado.

## Estrutura

```
currency-strength-ea/
├── config.py                          # universo de moedas/pares, período, paths — sem credenciais
├── src/
│   ├── pairs.py                        # gera os 28 pares cruzados (convenção base/quote de mercado)
│   ├── sessions.py                     # classifica timestamp UTC em sessão (Tóquio/Londres/NY/overlap)
│   ├── db.py                           # schema SQLite + upserts
│   ├── gaps.py                         # detecção de gaps de dado, compartilhada pelos dois downloaders
│   ├── mt5_connector.py                # wrapper de conexão MT5 (import lazy do pacote MetaTrader5)
│   └── dukascopy.py                    # decodificação do tick history .bi5 da Dukascopy + resample p/ M5
├── scripts/
│   ├── list_symbols.py                 # diagnóstico: descobre o sufixo de símbolo da conta MT5
│   ├── download_history.py             # baixa candles M5 via MT5 (limitado pela profundidade da conta)
│   ├── download_history_dukascopy.py   # baixa candles M5 via Dukascopy (não depende de MT5/Windows)
│   ├── dukascopy_smoke_test.py         # valida o parsing Dukascopy com UM arquivo real antes do backfill
│   ├── spread_sampler.py               # amostra spread bid/ask AO VIVO continuamente (via MT5)
│   └── spread_report.py                # agrega as amostras em relatório CSV/Markdown por par/sessão
├── tests/                               # testes de lógica pura (não dependem de MT5/Windows nem de rede)
├── reports/                             # relatórios gerados (dados reais são gitignored, só o .md fica)
└── data/                                # SQLite gerado localmente (gitignored)
```

## Como rodar

### Histórico de candles (via Dukascopy — qualquer SO com internet normal, não precisa de MT5)

1. Instalar dependências: `pip install -r requirements.txt`
2. Validar o parsing com um arquivo real antes de tudo:
   ```
   python -m scripts.dukascopy_smoke_test --pair EURUSD --date 2024-06-04 --hour 10
   ```
   Confira que os preços impressos são plausíveis (EURUSD ~1.0-1.2, não 0.0001 nem 100000) antes
   de seguir.
3. Rodar o backfill completo (demora — ver aviso de volume no topo do script; é resumível,
   pode interromper e rodar de novo):
   ```
   python -m scripts.download_history_dukascopy
   ```

### Spread real e (opcionalmente) histórico via MT5 (precisa de Windows + terminal Exness logado)

1. Definir variáveis de ambiente com as credenciais da conta (nunca colocar em arquivo versionado):
   ```
   set MT5_LOGIN=12345678
   set MT5_PASSWORD=sua_senha
   set MT5_SERVER=Exness-MT5Real8      # ou o servidor demo, conforme a conta usada
   ```
   Se a Exness expuser os símbolos com sufixo (ex: `EURUSDm` em vez de `EURUSD`), defina também
   `MT5_SYMBOL_SUFFIX` — descoberto rodando (não adivinhando na interface):
   ```
   python -m scripts.list_symbols
   ```
2. Rodar a amostragem de spread ao vivo, deixando rodar continuamente por pelo menos 2-3 semanas
   corridas para cobrir todas as sessões com volume suficiente de amostras:
   ```
   python -m scripts.spread_sampler
   ```
3. Gerar o relatório de spread por par/sessão a qualquer momento para ver o progresso
   (pares/sessões com menos de `--min-samples` amostras aparecem como "DADO INSUFICIENTE", nunca
   com um número estimado):
   ```
   python -m scripts.spread_report --min-samples 200
   ```
4. `download_history.py` (via MT5) continua disponível, mas está limitado pela profundidade de
   histórico M5 que a conta permitir — ver `reports/fase1_relatorio.md`.

### Testes (não precisam de MT5, Windows nem rede)

```
pytest tests/ -v
```

## Decisões de design tomadas nesta fase

- **Convenção base/quote dos 28 pares**: ordem de precedência de mercado
  `EUR > GBP > AUD > NZD > USD > CAD > CHF > JPY` (`src/pairs.py`). É a convenção padrão com que
  os pares já são cotados/expostos pelos brokers — não é uma escolha arbitrária, e importa para o
  sinal do retorno na decomposição de força (Seção 3.0 do estudo).
- **Janelas de sessão (Tóquio/Londres/NY/overlap) usadas aqui são só para segmentação descritiva
  do relatório de spread da Fase 1** — aproximações padrão de mercado em UTC, sem ajuste de
  horário de verão. Isso é diferente e não deve ser confundido com a definição final da "janela
  de sessão" do índice de força, que é decidida empiricamente no backtest (Fase 4).
- **Histórico de candles vem da Dukascopy, spread real vem só do MT5/Exness ao vivo** — nunca o
  contrário. O campo `spread` que o MT5 retorna em candles históricos, e o `broker_spread`
  calculado a partir dos ticks da Dukascopy, são guardados só como referência secundária —
  nenhum dos dois é a fonte do levantamento de spread da Fase 1 (Seção 6 do estudo), que exige
  amostragem ao vivo da corretora real.
- **Preço usado nos candles reconstruídos da Dukascopy é o mid ((ask+bid)/2), não o bid.** Evita
  embutir metade do spread na série de retorno usada para decompor a força (Seção 3.0) — o custo
  de spread é tratado à parte e uma única vez, no filtro de pares operáveis da Fase 3.
- **Detecção de gaps** (`src/gaps.py`, compartilhada pelos dois downloaders): registra em
  `data_gaps` qualquer intervalo entre candles consecutivos maior que ~3 dias (tolerando o gap
  normal de fim de semana). Recalculada sobre o histórico completo do par a cada execução, para
  não perder gaps de execuções anteriores nem duplicar registros ao retomar.

## O que falta para a Fase 1 estar de fato completa

Ver `reports/fase1_relatorio.md` para o estado atual e os próximos passos concretos.
