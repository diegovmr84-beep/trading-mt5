# Relatório — Fase 1: Coleta de dados e levantamento de spread

**Status: infraestrutura pronta e testada (26 testes); nenhum dado real coletado ainda.**

## Linha do tempo desta fase

1. Infraestrutura inicial escrita nesta sessão remota (sem MT5/internet aberta disponíveis):
   geração dos 28 pares, schema SQLite, conector MT5, scripts de download/amostragem/relatório.
2. Você abriu uma sessão local do Claude Code na sua máquina Windows, com o terminal MT5 da
   Exness já logado (conta `Exness-MT5Trial11`, trial/demo).
3. **Diagnóstico de símbolos**: a conta usa sufixo `m` em todos os 28 pares (`EURUSDm`,
   `GBPJPYm`, etc.) — 356 símbolos visíveis no total, 28/28 pares canônicos encontrados como
   `<PAR>m`. `MT5_SYMBOL_SUFFIX=m` confirmado.
4. **Download do histórico via MT5 bateu em dois limites independentes**, ambos específicos
   dessa conta/terminal, não bugs no código:
   - Limite de "Máx. barras no gráfico" do terminal (100.000) — qualquer pedido de M5 cobrindo
     mais de ~347 dias retorna `Invalid params`.
   - **A conta Trial só tem histórico M5 a partir de ~2025-05-02** — mesmo contornando o limite
     acima, o servidor da Exness não entrega M5 anterior a essa data para essa conta. Timeframes
     maiores (H1, H4, D1) têm histórico completo desde 2020 na mesma conta — o problema é
     específico do M5.
5. **Decisão tomada**: separar as duas fontes de dado em vez de mudar o timeframe do estudo para
   contornar a limitação da conta (mudar para H1 introduziria descompasso entre o timeframe do
   índice de força e o timeframe de execução — risco relevante que você mesmo levantou, e motivo
   correto para não fazer essa troca). Adotado:
   - **Histórico de candles M5 (2020+)**: via **Dukascopy** (tick history público, gratuito, sem
     cadastro), reconstruído para M5 localmente.
   - **Spread real por par/sessão**: continua exclusivamente via **MT5/Exness ao vivo** — isso
     não pode vir de outra fonte, é a exigência central da Seção 6 do estudo.
6. Implementados: `src/dukascopy.py` (decodificação do formato .bi5 + resample para M5),
   `scripts/download_history_dukascopy.py` (backfill completo, concorrente, resumível),
   `scripts/dukascopy_smoke_test.py` (validação com 1 arquivo real antes do backfill completo),
   `src/gaps.py` (detecção de gaps compartilhada entre os dois downloaders). 26 testes no total,
   todos passando.

## O que foi feito

- Geração determinística e testada dos 28 pares cruzados (`src/pairs.py`, 6 testes).
- Classificação de sessão UTC (`src/sessions.py`, 6 testes).
- Schema SQLite com 4 tabelas, todos os inserts upsert-safe (`src/db.py`, 5 testes).
- Detecção de gaps de dado compartilhada entre os dois caminhos de download (`src/gaps.py`,
  3 testes) — recalculada sobre o histórico completo a cada execução, sem duplicar registros ao
  retomar.
- Decodificação do tick history da Dukascopy: parsing do formato binário `.bi5` (LZMA + registros
  de 20 bytes), conversão para candles M5 usando preço médio (mid), com o formato validado por
  busca em múltiplas fontes independentes e testado com dados sintéticos (`src/dukascopy.py`,
  6 testes) — **ainda não validado contra um arquivo real** (ver limitações abaixo).
- Wrapper de conexão MT5 com credenciais só via variável de ambiente (`src/mt5_connector.py`).
- `scripts/list_symbols.py` — já rodado com sucesso na sua conta, confirmou sufixo `m`.
- `scripts/download_history.py` (via MT5) — já rodado; funcional, mas limitado a ~8 meses de M5
  pela profundidade de histórico da conta Trial.
- `scripts/download_history_dukascopy.py` — backfill completo via Dukascopy, com concorrência
  configurável, retry com backoff, e resumível (retoma do último candle salvo por par).
- `scripts/dukascopy_smoke_test.py` — baixa e decodifica UMA hora real para inspeção visual antes
  do backfill completo.
- `scripts/spread_sampler.py` / `scripts/spread_report.py` — prontos, ainda não rodados.

## O que NÃO foi feito (e por quê)

**Nenhum histórico de candles real (Dukascopy) e nenhuma amostra de spread real ainda existem.**

- O histórico M5 2020+ via Dukascopy não pôde ser baixado nem validado nesta sessão remota: o
  ambiente não tem acesso de rede à Dukascopy (só um allowlist restrito de hosts — testado e
  confirmado, não é instabilidade de rede). A lógica de decodificação foi testada só com dados
  sintéticos gerados aqui mesmo, não com um arquivo real.
- O levantamento de spread ao vivo ainda não foi iniciado na conta Trial (item independente do
  bloqueio de histórico — pode começar a qualquer momento).

Isso é reportado explicitamente em vez de simulado ou estimado, seguindo o mesmo princípio de
integridade que o estudo prévio exige para o backtest.

## Próximo passo concreto

Na sua máquina Windows (mesma sessão local do Claude Code já aberta):

1. `python -m scripts.dukascopy_smoke_test --pair EURUSD --date 2024-06-04 --hour 10` — conferir
   visualmente que os preços saem plausíveis antes de qualquer coisa.
2. Se plausível: `python -m scripts.download_history_dukascopy` (backfill completo — vai demorar
   horas, ver aviso de volume no script; pode rodar em background).
3. Em paralelo, `python -m scripts.spread_sampler` na conta Trial, rodando continuamente por
   2-3 semanas.
4. `python -m scripts.spread_report` para gerar o relatório de spread quando houver amostra
   suficiente.

## Limitações/decisões que precisam da sua revisão

- [x] Sufixo de símbolo da conta Exness: confirmado `m`.
- [ ] **Spread coletado na conta Trial precisa ser revalidado numa conta real antes da Fase 5** —
      contas demo por vezes simulam spread mais favorável do que uma conta real. Combinado
      anteriormente: pode começar a coleta na Trial agora, mas isso fica marcado como pendente de
      revalidação, não como definitivo.
- [ ] Confirmar se 2-3 semanas de amostragem contínua de spread é aceitável, ou se prefere outro
      período.
- [ ] Preço mid (não bid) usado para reconstruir os candles da Dukascopy — decisão documentada no
      README, revisar se concorda com a justificativa (separação do custo de spread, Seção 3.3).
- [ ] Revisar a convenção de base/quote dos 28 pares (`EUR > GBP > AUD > NZD > USD > CAD > CHF >
      JPY`).
- [ ] O histórico real dos candles Dukascopy (preços, contagem de gaps) ainda precisa ser revisado
      quando o backfill terminar — este relatório será atualizado com os números reais nessa hora.

## Pergunta em aberto do próprio estudo (Seção 10) — ainda não fechada

- [ ] Levantar dados reais de spread por par na Exness para calibrar os limites por par — depende
      da execução do `spread_sampler.py` acima.
