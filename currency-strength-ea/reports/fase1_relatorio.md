# Relatório — Fase 1: Coleta de dados e levantamento de spread

**Status: infraestrutura pronta e testada; execução real da coleta ainda PENDENTE.**

## O que foi feito

- Geração determinística e testada dos 28 pares cruzados dos 8 majors, na convenção base/quote
  de mercado padrão (`src/pairs.py`, 6 testes).
- Classificação de sessão (Tóquio/Londres/NY/overlap) por horário UTC, para uso descritivo no
  relatório de spread (`src/sessions.py`, 6 testes).
- Schema SQLite com 4 tabelas: `symbols`, `candles_m5`, `spread_samples`, `data_gaps`
  (`src/db.py`, 4 testes). Todos os inserts são upsert por chave (símbolo+timestamp), então
  rodar a coleta de novo não duplica dado.
- Wrapper de conexão MT5 com credenciais só via variável de ambiente, nunca em código
  (`src/mt5_connector.py`).
- `scripts/download_history.py`: baixa M5 de jan/2020 até hoje para os 28 pares, em blocos
  anuais, com detecção automática de gaps suspeitos (>3 dias entre candles consecutivos,
  tolerando o gap normal de fim de semana).
- `scripts/spread_sampler.py`: amostra bid/ask ao vivo continuamente, taggeado por par e sessão.
- `scripts/spread_report.py`: agrega as amostras em CSV + Markdown por par/sessão, com média,
  mediana e máximo — e rotula explicitamente como "DADO INSUFICIENTE" qualquer par/sessão abaixo
  do mínimo de amostras configurado, em vez de reportar um número não confiável.
- 16 testes automatizados, todos passando, cobrindo a lógica que não depende do terminal MT5.

## O que NÃO foi feito (e por quê)

**Nenhum dado real foi baixado. Nenhum número de spread real foi coletado.**

O ambiente onde esta sessão rodou é um container Linux sem o terminal MT5 instalado, sem
credenciais de conta Exness e sem acesso à rede da corretora. O pacote `MetaTrader5` só
funciona em Windows com o terminal MT5 rodando localmente. Portanto:

- O histórico de candles M5 (2020+, 28 pares) ainda não existe em nenhum banco.
- O levantamento de spread por par/sessão (Seção 6 do estudo, pré-requisito de alta prioridade
  para a Fase 5) ainda não tem nenhuma amostra real.

Isso é reportado explicitamente em vez de simulado ou estimado, seguindo o mesmo princípio de
integridade que o estudo prévio exige para o backtest (nunca apresentar preliminar/estimado como
validado).

## Próximo passo concreto (fora desta sessão)

Alguém com acesso a uma máquina Windows com o terminal MT5 da Exness instalado e logado precisa:

1. `pip install -r requirements.txt`
2. Definir `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` (e `MT5_SYMBOL_SUFFIX` se aplicável)
3. Rodar `python -m scripts.download_history`
4. Deixar `python -m scripts.spread_sampler` rodando por 2-3 semanas corridas
5. Rodar `python -m scripts.spread_report` e revisar o resultado

O arquivo `data/currency_strength.db` resultante (ou pelo menos o relatório de spread gerado)
precisa ser trazido de volta para esta revisão antes de eu prosseguir para a Fase 2, já que a
Fase 2 (cálculo do índice de força) depende do histórico de candles real, e a Fase 3 (filtro de
pares operáveis) depende do relatório de spread real.

## Limitações/decisões que precisam da sua revisão

- [ ] Confirmar se a conta Exness a ser usada expõe os símbolos sem sufixo (`EURUSD`) ou com
      sufixo (`EURUSDm` ou similar) — isso é só uma variável de ambiente (`MT5_SYMBOL_SUFFIX`),
      mas precisa ser checado antes de rodar.
- [ ] Confirmar se 2-3 semanas de amostragem contínua de spread é aceitável, ou se prefere um
      período diferente antes de considerar a Fase 1 completa.
- [ ] As janelas de sessão usadas para segmentar o relatório de spread (`src/sessions.py`) são
      aproximações padrão em UTC, sem ajuste de horário de verão — aceitável para o propósito
      descritivo desta fase, mas sinalizando aqui para não ser confundido com a decisão final de
      janela de sessão do índice de força (essa é decidida empiricamente na Fase 4).
- [ ] Revisar a convenção de base/quote adotada para os 28 pares (`EUR > GBP > AUD > NZD > USD >
      CAD > CHF > JPY`) — é a convenção padrão de mercado, mas listo aqui porque afeta o sinal
      usado em todo o resto do projeto.

## Pergunta em aberto do próprio estudo (Seção 10) — ainda não fechada

- [ ] Levantar dados reais de spread por par na Exness para calibrar os limites por par — é
      exatamente o que este item da Fase 1 endereça, mas ainda depende da execução real acima.
