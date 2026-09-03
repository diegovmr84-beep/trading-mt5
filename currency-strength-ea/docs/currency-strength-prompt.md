# Prompt para Claude Code — Currency Strength EA (MT5 / Forex)

## Contexto para o Claude Code

Este é o **Projeto 4** de um portfólio de automação de trading. Os outros projetos (Poly-Binance Agent, MT5 EA de índices, Chrome Extension) seguem um princípio rígido de **"no rush"**: nenhuma fase começa antes da entrega da fase anterior ser revisada e aprovada pelo usuário (Diego). Validação estatística e paper trading são obrigatórios antes de qualquer capital real. Este projeto segue o mesmo princípio.

**Regra fundamental de execução: pare ao final de cada fase e aguarde revisão explícita antes de prosseguir para a próxima.** Não implemente fases futuras adiantado, mesmo que pareça natural continuar.

Anexo a este prompt está o documento `estudo-previo-currency-strength.md`, que contém todas as decisões de design já fechadas. **Leia esse documento por completo antes de escrever qualquer código.** As decisões nele não são sugestões — são requisitos. Onde o documento diz "determinado empiricamente pelo backtest", isso significa: implemente o teste de múltiplos valores, não escolha um valor único por conta própria.

---

## Hipótese do projeto (resumo)

Cada moeda individual (dos 8 majors: USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD) tem uma "força" relativa que pode ser estimada agregando seu comportamento contra os outros 7. Operar pares onde uma moeda está consistentemente forte contra a maioria da cesta, cruzada com uma moeda consistentemente fraca, pode ter expectativa positiva — mas isso é uma hipótese a validar estatisticamente, não uma verdade assumida.

**Princípio não-negociável:** força ≠ variação de preço de um par isolado. O preço de USD/JPY sozinho não distingue "USD forte" de "JPY fraco". O índice de força precisa decompor isso usando o máximo de pares cruzados disponíveis.

---

## Fase 1 — Coleta de dados e levantamento de spread

**Objetivo:** ter os dados históricos e o levantamento de custo real de execução antes de qualquer cálculo de sinal.

1. Conectar ao MT5 (conta Exness) e baixar candles M5 dos 8 majors, cobrindo todos os 28 pares cruzados possíveis, de janeiro/2020 até hoje.
2. Armazenar em SQLite, seguindo o padrão já usado no poly-binance-agent (schema similar, se fizer sentido reaproveitar).
3. **Levantamento de spread por par** (prioridade alta, é pré-requisito para a Fase 5):
   - Para cada um dos 28 pares: spread médio e spread máximo observado, segmentado por sessão (Tóquio/Londres/NY/overlap) e por horário de baixa liquidez
   - Isso é dado de mercado real, não deve ser assumido ou estimado sem coleta
   - Produzir uma tabela/relatório simples com esses números — vai virar input direto da Fase 5 (limite de spread aceitável por par)
4. Documentar qualquer limitação encontrada (ex: histórico incompleto para algum par, gaps de dados) antes de prosseguir.

**Deliverable da Fase 1:** dataset armazenado + relatório de spread por par/sessão. Aguardar revisão antes da Fase 2.

---

## Fase 2 — Cálculo do índice de força (sem execução, sem geração de trades ainda)

**Objetivo:** implementar o índice de força e produzir uma série temporal de valores — não gerar sinais de entrada ainda, essa é a Fase 3.

1. Implementar **dois métodos em paralelo**, comparáveis entre si:
   - **Método A (primário, v1):** força(X) = média aritmética simples dos retornos de X contra as outras 7 moedas, usando os 28 pares cruzados completos (sem filtro de spread nesta etapa — ver princípio de separação abaixo)
   - **Método C (checagem de robustez):** mesmo cálculo de base, convertido em ranking ordinal (1º a 8º mais forte) a cada timestamp
2. **Separação obrigatória de estágios**: o cálculo do índice usa todos os 28 pares, independente de serem depois operáveis por spread. O filtro de spread só entra na Fase 3, na seleção de pares candidatos a trade — nunca no cálculo do índice em si.
3. **Regra anti-lookahead**: o índice no timestamp T só pode usar dados até o fechamento do candle T-1. Implementar testes automatizados que verifiquem isso explicitamente (não confiar só em revisão manual de código).
4. **Janela de cálculo — sessão do dia, definição a determinar empiricamente**: implementar as três variantes candidatas como parâmetro configurável, não hardcoded:
   - (a) dia corrido 00:00–23:59 UTC
   - (b) sessão clássica específica (Tóquio/Londres/NY)
   - (c) janela de overlap de maior liquidez (Londres/NY)
   - A escolha entre elas é feita na Fase 4 (validação), com base em dados — aqui na Fase 2 apenas garanta que o código suporta as três sem retrabalho.
5. Produzir a série temporal de força para as 8 moedas, pelos dois métodos (A e C), para todo o período histórico.
6. **Comparação A vs. C**: gerar um relatório simples mostrando onde os dois métodos concordam/discordam. Divergências grandes e frequentes merecem nota explícita — não decida sozinho se isso invalida o método, apenas documente para revisão.

**Nota sobre mínimos quadrados:** NÃO implementar nesta fase. É uma evolução condicional (ver Seção 3.1 do estudo prévio) que só entra depois que a Fase 4 mostrar se o Método A é insuficiente. Implementá-lo agora seria antecipar uma decisão que depende de resultado de validação ainda não obtido.

**Deliverable da Fase 2:** série temporal de força (métodos A e C) + relatório de comparação entre eles. Aguardar revisão antes da Fase 3.

---

## Fase 3 — Geração de sinais e regras de entrada/saída (ainda sem execução real)

**Objetivo:** transformar a série de força em sinais de trade candidatos, aplicando os critérios definidos no estudo — mas ainda em modo de simulação/histórico, não execução.

1. **Critério de entrada — amplitude/consistência, não diferença de extremos**: implementar o critério revisado — a moeda candidata precisa estar significativamente mais forte que a maioria (ou todas) das outras 7, não apenas mais forte que a moeda mais fraca isolada. Implementar como parâmetro configurável o limiar mínimo de moedas "vencidas com significância" (testar 5 de 7, 6 de 7, 7 de 7).
   - Definir precisamente o teste estatístico usado para "significativo" por comparação individual dentro da cesta (documentar a escolha, não deixar implícito no código).
2. **Filtro de pares operáveis por spread**: aqui, sim, aplicar o filtro de spread (usando o levantamento da Fase 1). Lista de candidatos ordenada pelo ranking de força; cada candidato só vira trade se o spread ao vivo/histórico estiver dentro do limite aceitável calibrado por par. Modelar isso no backtest desde o início — não é filtro só de execução ao vivo.
3. **Número de posições simultâneas: dinâmico**, resultado natural do filtro acima — não fixar um número.
4. **Stop/take**: calibrar empiricamente a relação entre intensidade do sinal de força e magnitude de movimento subsequente do par, **usando exclusivamente o período de desenvolvimento (70% dos dados)**. Não usar dados do período de validação nesta calibração sob nenhuma circunstância — isso é regra de integridade estatística, não sugestão de estilo.
5. Gerar a lista histórica de trades candidatos (ainda não é backtest de P&L completo — isso é Fase 4).

**Deliverable da Fase 3:** lógica de geração de sinais implementada e documentada, com todos os parâmetros configuráveis (não hardcoded) prontos para a varredura de validação da Fase 4. Aguardar revisão antes da Fase 4.

---

## Fase 4 — Backtest e validação estatística completa

**Objetivo:** rodar o backtest real e aplicar o protocolo de validação estatística — esta é a fase que decide se o projeto segue para dimensionamento/alavancagem ou volta para redesenho.

1. **Split obrigatório**: 70% desenvolvimento / 30% validação (out-of-sample). Nenhum parâmetro pode ser ajustado olhando o período de validação.
2. **Varredura de parâmetros no período de desenvolvimento**, testando:
   - As 3 variantes de "sessão do dia" (Fase 2, item 4)
   - Os limiares de amplitude de força (5/6/7 de 7, Fase 3, item 1)
   - Reportar qual combinação produz melhor resultado, mas **sem ainda declarar validado** — isso só acontece depois do teste em out-of-sample
3. **Correção de Bonferroni — atenção especial**: o número de testes a corrigir inclui tanto a varredura de parâmetros (item 2 acima) quanto os testes de significância internos por par dentro da cesta (até 7 comparações por moeda candidata, Fase 3 item 1). Ambas as camadas entram na contagem total de testes usada no ajuste — documentar explicitamente essa contagem no relatório de validação.
4. **Tamanho mínimo de amostra configurável**: qualquer resultado abaixo do mínimo definido deve ser rotulado explicitamente como "preliminar" no relatório e em qualquer output — nunca apresentado como validado.
5. **Magnitude mínima de efeito**: definir e aplicar um critério análogo ao \|r\| > 0.3 do poly-binance-agent, aqui expresso como expectativa positiva mínima por trade após custos.
6. **Walk-forward analysis**: revalidar em janelas móveis (ex: treina 6 meses, testa o mês seguinte, desliza) para checar estabilidade do edge ao longo do tempo.
7. **Controle de correlação entre pares**: trades em pares que compartilham moeda-base não são amostras independentes — o cálculo de significância precisa considerar isso (agrupamento por cluster de moeda).
8. **Sensibilidade a custos**: rodar o backtest completo em 3 cenários de custo (otimista/realista/pessimista de spread+slippage, usando os dados reais da Fase 1). Reportar todos os três — se só o cenário otimista é positivo, isso precisa aparecer com destaque no relatório, não ficar escondido.
9. **Validação em out-of-sample**: aplicar os parâmetros escolhidos no desenvolvimento (item 2) ao período de validação nunca visto, sem reajuste algum. Reportar o resultado tal como sair.
10. **Decisão sobre mínimos quadrados**: se o resultado passar nos três critérios cumulativos (Bonferroni + amostra mínima + magnitude de efeito) com folga, mínimos quadrados não é necessário agora. Se passar raspando ou mostrar concentração de erro em pares específicos de spread alto/liquidez baixa, documentar isso como recomendação explícita para uma iteração futura com mínimos quadrados (não implementar automaticamente — aguardar decisão do usuário).

**Deliverable da Fase 4:** relatório de validação estatística completo, incluindo todos os itens acima, com veredito claro: **validado / preliminar / não validado**. Este relatório é o gate de decisão — a Fase 5 (alavancagem) só começa se o resultado for "validado" (não "preliminar"). Aguardar revisão e aprovação explícita do usuário antes de prosseguir, independente do resultado.

---

## Fase 5 — Estudo de alavancagem e risco (condicional à aprovação da Fase 4)

**Não iniciar esta fase se a Fase 4 não tiver resultado "validado".**

1. Estudo de risco, não de retorno — o objetivo é entender o quanto a alavancagem amplifica drawdown, não "quanto dá pra ganhar".
2. Relação entre alavancagem e magnitude de drawdown esperado, usando a variância observada no backtest validado.
3. Simulação de risco de ruína: dado o tamanho de amostra e variância reais, que nível de alavancagem mantém a probabilidade de estourar a conta abaixo de um limiar aceitável (a definir com o usuário).
4. Diferenciar alavancagem nominal da corretora (o que a Exness permite) de alavancagem efetiva (tamanho de posição / capital) — são conceitos diferentes, não confundir no relatório.
5. Cenário de stress: aplicar o pior drawdown histórico observado no backtest à alavancagem proposta e mostrar o resultado em termos concretos (% de capital, não só abstrato).

**Deliverable da Fase 5:** relatório de risco com recomendação de faixa de alavancagem, não um número único "otimizado". Aguardar revisão antes da Fase 6.

---

## Fase 6 — Paper trading (conta demo)

**Não iniciar sem aprovação explícita da Fase 5.**

1. Implementar a execução em conta demo Exness, replicando exatamente a lógica validada (sem "melhorias" de última hora não testadas).
2. Período mínimo de observação a definir com o usuário antes de começar — não decidir isso sozinho.
3. Comparar performance ao vivo (demo) contra o que o backtest previu para o mesmo período, e reportar divergências.

---

## Fase 7 — Capital real (pequeno)

**Não iniciar sem aprovação explícita da Fase 6**, e apenas se a Fase 6 mostrar performance consistente com o backtest.

1. Definir com o usuário, antes de começar, os critérios objetivos de stop que desligam o EA automaticamente se a performance ao vivo divergir do validado (ex: drawdown além de X%, ou Y trades perdedores consecutivos além do esperado estatisticamente).
2. Começar com capital mínimo viável, escalar apenas após período adicional de observação definido previamente.

---

## Lembretes gerais para todas as fases

- Nunca escolher um parâmetro "porque parece certo" quando o documento de design especifica que ele deve ser determinado empiricamente — implementar a varredura, não pular direto para um valor.
- Sempre separar claramente cálculo de sinal (Fase 2/3) de execução (Fase 6/7) — a arquitetura do código deve refletir essa separação, não só a documentação.
- Qualquer resultado "bonito demais" no backtest é motivo de suspeita, não de comemoração — checar lookahead bias, overfitting de parâmetro, ou vazamento de dados de validação antes de reportar como sucesso.
- Ao final de cada fase, produzir um resumo claro do que foi feito, o que foi encontrado, e quais decisões ainda estão em aberto — no mesmo formato dos relatórios de fase já usados nos outros projetos do portfólio.
