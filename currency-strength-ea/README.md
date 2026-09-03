# Currency Strength EA — Fase 1: coleta de dados e levantamento de spread

Projeto 4 do portfólio, independente do EA de índices. Ver `estudo-previo-currency-strength.md`
e `currency-strength-prompt.md` (anexados na conversa que originou este projeto) para o design
completo e o plano de fases. Este diretório implementa a **Fase 1**.

## ⚠️ Limitação importante desta sessão

O pacote `MetaTrader5` (usado para falar com o terminal MT5) **só funciona em Windows**, e
requer o terminal MT5 instalado e logado numa conta Exness real ou demo. O ambiente onde este
código foi escrito é um container Linux, sem terminal MT5, sem acesso à rede da corretora e sem
credenciais — portanto **os scripts de coleta não foram executados aqui, e nenhum dado ou número
de spread neste diretório é real**. O que foi entregue é o código completo e testado da
infraestrutura de coleta; a execução real precisa acontecer na sua máquina (ou outra com o
terminal MT5/Exness disponível).

Nada neste projeto usa números inventados como se fossem dados de mercado — isso violaria o
princípio central do estudo prévio (Seção 6: "é dado de mercado real, não deve ser assumido ou
estimado sem coleta").

## Estrutura

```
currency-strength-ea/
├── config.py                  # universo de moedas/pares, período, paths — sem credenciais
├── src/
│   ├── pairs.py                # gera os 28 pares cruzados (convenção base/quote de mercado)
│   ├── sessions.py             # classifica timestamp UTC em sessão (Tóquio/Londres/NY/overlap)
│   ├── db.py                   # schema SQLite + upserts
│   └── mt5_connector.py        # wrapper de conexão MT5 (import lazy do pacote MetaTrader5)
├── scripts/
│   ├── download_history.py     # baixa candles M5 2020+ dos 28 pares para o SQLite
│   ├── spread_sampler.py       # amostra spread bid/ask AO VIVO continuamente
│   └── spread_report.py        # agrega as amostras em relatório CSV/Markdown por par/sessão
├── tests/                       # testes de lógica pura (não dependem do MetaTrader5/Windows)
├── reports/                     # relatórios gerados (dados reais são gitignored, só o .md fica)
└── data/                        # SQLite gerado localmente (gitignored)
```

## Como rodar (na máquina com MT5/Exness)

1. Instalar dependências:
   ```
   pip install -r requirements.txt
   ```
2. Definir variáveis de ambiente com as credenciais da conta (nunca colocar em arquivo versionado):
   ```
   set MT5_LOGIN=12345678
   set MT5_PASSWORD=sua_senha
   set MT5_SERVER=Exness-MT5Real8      # ou o servidor demo, conforme a conta usada
   ```
   Se a Exness expuser os símbolos com sufixo (ex: `EURUSDm` em vez de `EURUSD`), defina também:
   ```
   set MT5_SYMBOL_SUFFIX=m
   ```
3. Baixar o histórico (roda uma vez; pode ser interrompido e retomado — upsert por timestamp):
   ```
   python -m scripts.download_history
   ```
4. Rodar a amostragem de spread ao vivo, deixando rodar continuamente por pelo menos 2-3 semanas
   corridas para cobrir todas as sessões com volume suficiente de amostras:
   ```
   python -m scripts.spread_sampler
   ```
5. Gerar o relatório de spread por par/sessão (pode ser rodado a qualquer momento para ver o
   progresso; pares/sessões com menos de `--min-samples` amostras aparecem como "DADO
   INSUFICIENTE", nunca com um número estimado):
   ```
   python -m scripts.spread_report --min-samples 200
   ```
6. Rodar os testes (não precisam do MT5, rodam em qualquer SO):
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
- **Spread histórico não é reconstruído a partir do candle baixado.** O campo `spread` que o MT5
  retorna em candles históricos não é garantidamente confiável como fonte de spread real
  histórico (depende de como cada corretora armazena esse dado). Por isso o levantamento de
  spread do estudo (Seção 6) é feito por **amostragem ao vivo contínua** (`spread_sampler.py`),
  não a partir do histórico de candles. O campo `broker_spread` é armazenado em `candles_m5`
  apenas como referência secundária, não como fonte da Fase 1.
- **Detecção de gaps**: `download_history.py` registra em `data_gaps` qualquer intervalo entre
  candles consecutivos maior que ~3 dias (tolerando o gap normal de fim de semana). Isso ainda
  precisa ser revisado manualmente após uma execução real para documentar limitações encontradas,
  conforme pede o item 4 da Fase 1.

## O que falta para a Fase 1 estar de fato completa

Ver `reports/fase1_relatorio.md` para o estado atual e os próximos passos concretos.
