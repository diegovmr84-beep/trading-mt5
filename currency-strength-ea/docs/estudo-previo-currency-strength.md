# Estudo Prévio — Currency Strength EA (MT5 / Forex)

**Projeto 4 do portfólio.** Separado do EA de índices (US30/US500/USTEC). Segue o mesmo princípio "no rush": validação estatística → paper trading → capital pequeno real. Nenhuma fase começa sem revisão da entrega anterior.

Status: **Fase 0 — Estudo/Design**. Nenhum código de execução deve ser escrito antes deste documento ser revisado e aprovado.

---

## 1. Contexto e hipótese central

**Hipótese a testar:** cada moeda individual carrega um "momentum" ou "força" relativa que pode ser estimada agregando seu comportamento contra uma cesta de outras moedas. Operar o par formado pela moeda mais forte contra a mais fraca do momento tem expectativa positiva maior do que operar um par isolado, porque o sinal está sendo confirmado por múltiplas fontes (múltiplos pares) em vez de uma só.

**O que isso NÃO é:** não é um indicador proprietário nem "segredo" de mercado. É uma forma de agregação de sinal de momentum de curto prazo. Se tiver edge, ele é pequeno, sensível a custo de transação, e precisa ser provado — não assumido.

**Por que o backtest anterior provavelmente falhou** (a confirmar durante a auditoria do código antigo, se ele existir):
1. Definição de "força" instável ou mal especificada matematicamente
2. Lookahead bias (uso de dados do candle ainda em formação no cálculo do índice de força)
3. Pares tratados como amostras independentes quando, na verdade, compartilham a mesma moeda-base (correlação inflando falsa significância)
4. Janela/horário "ótimo" escolhido olhando o próprio período testado (overfitting)
5. Custos de transação (spread, slippage) não modelados ou subestimados em estratégia de giro curto

---

## 2. Escopo definido

| Parâmetro | Decisão |
|---|---|
| Universo de moedas | Majors: USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD |
| Pares derivados | Os 28 pares cruzados possíveis entre as 8 moedas (nem todos precisam ser operados — ver Seção 5) |
| Plataforma de dados/sinal | MT5 (Exness) |
| Timeframe | M5, padrão já usado nos outros projetos |
| Período histórico | Janeiro/2020 em diante |
| Projeto relacionado | Independente do EA de índices — sem compartilhamento de código além de utilitários genéricos (ex: módulo de validação estatística, se fizer sentido reaproveitar) |

---

## 3. Definição formal do índice de força (decidido nesta fase — detalhamento pendente)

Este é o ponto mais crítico do estudo — precisa ser fechado **antes** de qualquer backtest, com definição matemática exata, não descritiva.

### 3.0 Princípio estrutural: força ≠ variação de preço

Ponto central do estudo, não um detalhe técnico. O retorno de um par isolado (ex: USD/JPY subindo 0,3%) mistura dois efeitos indistinguíveis: USD pode estar forte, OU JPY pode estar excepcionalmente fraco — o preço do par sozinho não diz qual. Para isolar a força de **cada moeda individualmente**, é preciso decompor o preço de cada par nos seus dois componentes, usando o sistema formado por **todos os pares cruzados disponíveis envolvendo aquela moeda** como equações simultâneas.

Consequência direta: **quanto mais pares cruzados entrarem no cálculo do índice, mais estável e confiável a decomposição** — isso é matematicamente equivalente a ter mais equações para resolver o mesmo número de incógnitas (8 moedas). Por isso, o cálculo do índice de força usa o **universo máximo de pares cruzados disponíveis (até 28)**, independentemente de esses pares serem depois operáveis ou não (ver Seção 3.3 — essa é uma decisão separada).

### 3.1 Métodos primários (A e C, em paralelo — B mantida como enriquecimento futuro)

**Opção A — Retorno médio contra a cesta (método primário 1)**
Para cada moeda X, força(X) = média dos retornos percentuais de X contra todas as outras 7 moedas, usando todos os pares cruzados disponíveis onde X aparece (ajustando o sinal conforme X é base ou cotação no par).
- Simples, interpretável, auditável linha a linha
- Dá magnitude, não só ranking — permite medir "quão forte", não só "quem é mais forte"

**Método de resolução escolhido para a v1: média aritmética simples.** Decisão fechada, com justificativa registrada:
- Zero graus de liberdade adicionais (nenhum parâmetro extra a ajustar) — menor risco de overfitting logo na v1
- Totalmente auditável na mão — cada valor de força pode ser conferido manualmente, o que é valioso numa primeira validação
- Com 7 pares por moeda, a média já dilui razoavelmente o efeito de um outlier isolado — a robustez adicional de um método mais sofisticado tende a ser marginal nesse tamanho de amostra

**Mínimos quadrados — mantido como possibilidade explícita, não descartado, condicionado a evidência.** Em vez de média simples, o sistema de equações (retorno de cada par = força da base − força da cotada + erro) pode ser resolvido minimizando o erro quadrático total, o que dá peso implicitamente menor a pares que destoam do restante do sistema — potencialmente mais robusto a pares ruidosos/pouco líquidos (ex: NZD/JPY), à custa de mais complexidade de código e mais parâmetros de implementação, portanto mais superfície para overfitting sutil.

**Regra de decisão entre os dois:** a v1 roda com média simples e passa pelo protocolo de validação estatística completo (Seção 4).
- Se passar nos três critérios com folga → estratégia validada, mínimos quadrados não é necessário nesse momento
- Se passar raspando, ou falhar de um jeito que pareça concentrado em pares específicos de ruído/liquidez baixa → mínimos quadrados vira hipótese testável de melhoria em fase posterior, comparado A/B diretamente contra a v1 de média simples, usando os mesmos dados e mesmo protocolo estatístico
- O método C (ranking, abaixo) serve de checagem barata nesse meio-tempo: se A e C derem sinais parecidos, é indício de que ruído de par individual não está distorcendo tanto o resultado, o que reduz a urgência de migrar para mínimos quadrados

**Opção C — Rank-based (método primário 2, para comparação/robustez)**
Mesmo cálculo de base, mas convertido em ranking ordinal (1º a 8º mais forte) a cada timestamp, em vez de usar a magnitude bruta.
- Mais robusto a outliers e a diferenças de volatilidade entre pares
- Serve como checagem de robustez: se A e C derem sinais de entrada muito diferentes, é sinal de que a magnitude de A está sendo distorcida por outlier — vale investigar antes de confiar no resultado

**Opção B — Índice ponderado por peso econômico/liquidez (mantida, não descartada)**
Documentada e não descartada, como você apontou — mas entra como parâmetro de enriquecimento sobre A/C, não como método concorrente isolado da v1. Motivo prático: introduz pesos externos (relevância econômica de cada moeda) que são eles próprios estimativas sujeitas a viés, e adicionam graus de liberdade que facilitam overfitting se testados prematuramente. Fica planejada para uma fase posterior, aplicada sobre o método (A ou C) que se mostrar mais robusto na validação estatística.

### 3.2 Parâmetros a fixar (cada um precisa de justificativa, não só "porque sim")
- **Janela de cálculo do retorno: sessão do dia (decidido). Definição exata determinada empiricamente pelo backtest, não fixada a priori.** O backtest testa as três variantes candidatas — (a) dia corrido 00:00–23:59 UTC, (b) sessão clássica específica (Tóquio/Londres/NY), (c) janela de overlap de maior liquidez (tipicamente Londres/NY) — no período de desenvolvimento (70%), e reporta qual produz o índice de força mais estável/preditivo segundo o protocolo de validação estatística (Seção 4). A variante escolhida deve ser validada depois no período de out-of-sample (30%) para confirmar que não foi um ajuste específico ao período de desenvolvimento.
- Frequência de atualização do índice (a cada candle fechado? a cada N candles dentro da sessão?)
- Tratamento de gaps de fim de semana / feriados
- **Regra anti-lookahead explícita**: o índice no timestamp T só pode usar dados até o fechamento do candle T-1

### 3.3 Separação entre cálculo do índice e seleção de pares operáveis

Dois estágios distintos, que não devem ser misturados no código nem na validação:

1. **Cálculo do índice de força**: usa o máximo de pares cruzados disponíveis (até 28), independente de spread — aqui o objetivo é estimar força/fraqueza real, e restringir por spread nesse estágio prejudicaria a qualidade da decomposição (menos equações, estimativa menos estável).
2. **Seleção de pares operáveis**: filtro aplicado *depois* do índice calculado, sobre a lista de pares candidatos a trade, baseado em spread ao vivo por par. Ver Seção 5 para a lógica de decisão dinâmica (ex: ranking aponta NZD/JPY como par mais forte-vs-fraco, mas spread inviável no momento → EA pula para o próximo par do ranking com spread aceitável).

---

## 4. Protocolo de validação estatística (herda o padrão do poly-binance-agent)

Mesmos três critérios cumulativos já usados no outro projeto, adaptados para série temporal de trades:

1. **Correção de Bonferroni** — se o estudo testar múltiplas variações de parâmetros (janelas, thresholds), o p-value crítico precisa ser ajustado pelo número de testes realizados, não usar 0.05 fixo ingenuamente. **Atenção especial**: o critério de entrada agora envolve um teste de significância *por par* dentro da cesta (Seção 5 — "significativamente mais forte que quantas das outras 7"), o que multiplica o número de testes estatísticos por timestamp (até 7 comparações por moeda candidata). Isso precisa entrar explicitamente na contagem de testes usada no ajuste de Bonferroni, tanto nessa camada interna quanto na camada externa de escolha de parâmetros (janela de sessão, limiar 5/6/7, etc.) — do contrário o critério fica otimista demais e o "sinal validado" pode ser em parte artefato de múltiplas comparações não corrigidas.
2. **Tamanho mínimo de amostra configurável**, com qualquer resultado abaixo do mínimo explicitamente rotulado como **"preliminar"** — nunca apresentado como validado
3. **Magnitude mínima de efeito**, análogo ao \|r\| > 0.3 do outro projeto — aqui provavelmente expresso como expectativa positiva mínima por trade após custos, não só "taxa de acerto"

### 4.1 Camadas adicionais específicas de estratégia de trade (além do que já existe no outro projeto)

- **Split out-of-sample obrigatório**: nunca escolher parâmetros olhando o período inteiro. Sugestão: 70% desenvolvimento / 30% validação, com a validação nunca vista durante o ajuste de parâmetros.
- **Walk-forward analysis**: revalidar em janelas móveis (ex: treina em 6 meses, testa no mês seguinte, desliza) para checar se o "edge" é estável ao longo do tempo ou só existiu num regime de mercado específico.
- **Controle de correlação entre pares**: se vários pares operados compartilham moeda-base, os trades não são estatisticamente independentes — o cálculo de significância precisa considerar isso (ex: agrupar por cluster de moeda, não tratar cada trade como amostra i.i.d.)
- **Sensibilidade a custos**: rodar o mesmo backtest com 3 cenários de custo (otimista/realista/pessimista de spread+slippage) e reportar todos — se o resultado só é positivo no cenário otimista, isso precisa ficar explícito, não escondido.

---

## 5. Regras de entrada/saída (esqueleto a preencher com o Claude Code)

**Número de pares simultâneos: dinâmico, condicionado a spread por par — não um número fixo.** Decisão confirmada: como o spread varia muito por par e por horário (ex: NZD/JPY pode ter spread alto o suficiente para a operação já nascer negativa), o EA não deve ter um número fixo de posições simultâneas. Em vez disso:

- O ranking de força gera uma lista ordenada de candidatos (par mais forte-vs-mais fraco, segundo, terceiro...)
- Cada candidato só vira trade se o spread ao vivo estiver abaixo de um limite máximo aceitável, calibrado por par (spread viável de NZD/JPY é diferente de EUR/USD)
- O EA percorre a lista de candidatos e opera todos os que passarem no filtro de spread no momento — pode ser 1, pode ser vários, pode ser zero
- Isso precisa ser modelado no backtest desde o início (não é um filtro de execução ao vivo só) — senão o backtest superestima performance ao assumir spread ideal em pares que na prática nunca teriam spread viável

Ainda em aberto — decisões a tomar durante a fase de design detalhado:

- **Critério de entrada: amplitude/consistência estatística da força através da cesta — não diferença entre os dois extremos do ranking (decidido, mecanismo a determinar empiricamente).** Decisão revista: em vez de operar com base só na diferença entre a moeda mais forte e a mais fraca do momento (1º vs 8º do ranking), o sinal de entrada exige que a moeda candidata esteja **estatisticamente mais forte que a maioria (ou todas) das outras 7**, não apenas mais forte que uma única moeda fraca isolada. Isso evita operar um "pico" de força que na verdade é só ruído concentrado num par específico, e exige força ampla e consistente através da cesta inteira — mais alinhado ao princípio da Seção 3.0 (força é uma propriedade agregada da moeda, não do par isolado).
  - **Limite mínimo de moedas ("vencidas" com significância) para virar candidato: não fixado a priori.** O backtest testa diferentes limiares (ex: significativamente mais forte que pelo menos 5 de 7, 6 de 7, ou todas as 7) no período de desenvolvimento, e reporta qual produz a melhor relação entre frequência de sinal e qualidade/expectativa do trade, validado depois em out-of-sample.
  - Definição de "significativo" nesse contexto (por par individual dentro da cesta) precisa ser explicitada no código: provavelmente um teste estatístico por par contra o histórico recente de retornos daquele par, não apenas "força(X) > força(Y)" na comparação bruta — a ser detalhado na fase de implementação.
- **Regra de saída: stop/take calibrado empiricamente pela magnitude do movimento associado a cada nível de força/fraqueza (decidido, mecanismo a implementar).** O backtest mede, para diferentes níveis de intensidade do sinal de força, o quanto o par historicamente se move em seguida — e o stop/take nasce dessa relação medida, não de um valor arbitrário fixo (ex: não "50 pips" cravado). **Regra crítica de integridade estatística: essa calibração é feita exclusivamente no período de desenvolvimento (70%, ver Seção 4.1) — nunca olhando os dados do período de validação (30%)**, senão a calibração do stop/take vira uma forma sutil de overfitting disfarçada de "resultado de backtest".
- Janela de sessão: operar 24h ou restringir a horários de maior liquidez (Londres/NY overlap)? Isso precisa ser testado, não assumido por "todo mundo fala que overlap é melhor"
- Limite máximo de spread aceitável por par — precisa de levantamento de dados reais da Exness (ver Seção 6) antes de virar número fixo no código

---

## 6. Custos de execução reais (Exness)

A levantar antes do backtest — **prioridade alta**, já que a viabilidade por spread agora é parte estrutural da lógica de entrada (Seção 5), não só um ajuste fino de custo:
- Spread médio e spread máximo observado, por par, nos 28 cruzados — em horário de liquidez normal vs. baixa liquidez (ex: sessão asiática costuma ter spread pior em cross pairs como NZD/JPY)
- A partir disso, definir o limite de spread aceitável por par (input da Seção 5), não um valor único genérico para todos os pares
- Slippage esperado em ordens a mercado (dado histórico ou estimativa conservadora)
- Swap/rollover — relevante mesmo em trades curtos se alguma posição atravessar a virada do dia
- Comissão, se a conta Exness usada for de conta com comissão fixa em vez de spread puro

---

## 7. Alavancagem — estudo de risco, não de retorno

Conforme sua prioridade: entender o risco real antes de decidir o valor a usar. Isso vira uma seção própria de análise, não um parâmetro escolhido a priori. Deve cobrir:

- Relação entre alavancagem e magnitude de drawdown esperado (não só retorno esperado)
- Simulação de "risco de ruína": dado o tamanho de amostra e a variância observada no backtest validado, qual alavancagem levaria a probabilidade de estourar a conta a um nível aceitável?
- Diferença entre alavancagem nominal da corretora (o que a Exness permite) e alavancagem efetiva usada (tamanho de posição / capital) — são coisas diferentes e é comum confundir
- Cenário de stress: o que acontece no pior drawdown histórico observado no backtest, aplicado à alavancagem proposta?

**Esta seção só deve ser preenchida com números depois que a Seção 4 (validação estatística) tiver um resultado que passe nos três critérios cumulativos.** Definir alavancagem antes de validar a estratégia é inverter a ordem que gerou problema nos testes anteriores.

---

## 8. Ordem de execução proposta (fases)

1. **Fase 0** (este documento): fechar definição formal do índice de força, escopo de pares, protocolo estatístico
2. **Fase 1**: coleta de dados históricos M5 (2020+) para os 8 majors via MT5/Exness, armazenamento (SQLite, seguindo o padrão dos outros projetos)
3. **Fase 2**: implementação do cálculo de força + geração de sinais históricos (sem execução) — output é uma série temporal de sinais, não trades
4. **Fase 3**: backtest estatístico completo com os critérios da Seção 4, incluindo custos e out-of-sample
5. **Fase 4**: SE (e somente se) Fase 3 passar nos critérios — estudo de alavancagem e dimensionamento (Seção 7)
6. **Fase 5**: paper trading em conta demo Exness, período mínimo a definir, antes de qualquer capital real
7. **Fase 6**: capital real pequeno, com critérios de stop predefinidos para desligar o EA se a performance ao vivo divergir do validado

Cada fase gera um deliverable revisável antes da próxima começar — mesmo padrão dos outros projetos do portfólio.

---

## 9. Decisões fechadas nesta rodada

- [x] Métodos primários: **A (retorno médio contra a cesta) e C (rank-based) em paralelo**, comparados entre si como checagem de robustez. Opção B (índice ponderado por peso econômico) **mantida, não descartada** — entra como enriquecimento em fase posterior, aplicada sobre o método vencedor.
- [x] **Resolução do sistema na Opção A: média aritmética simples na v1.** Mínimos quadrados mantido como possibilidade explícita, não descartado — vira hipótese de melhoria testável em fase posterior, condicionado ao resultado da validação estatística da v1 (ver regra de decisão na Seção 3.1)
- [x] Cálculo do índice de força usa o **máximo de pares cruzados possível (até 28)** — spread não filtra essa etapa, só a etapa de seleção de pares operáveis (Seção 3.3)
- [x] Sem código/teste anterior de currency strength — projeto começa do zero (diferente do poly-binance-agent, que teve Fase 0 de auditoria; aqui a Fase 0 é só este documento de design)
- [x] Número de pares operados simultaneamente é **dinâmico**, condicionado a spread viável por par no momento — não um número fixo (Seção 5)
- [x] **Janela de cálculo do índice: sessão do dia — definição exata (UTC corrido / sessão clássica / overlap Londres-NY) determinada empiricamente pelo backtest**, validada em out-of-sample para confirmar que não é ajuste específico ao período de desenvolvimento (Seção 3.2)
- [x] **Critério de entrada revisado: amplitude/consistência estatística da força através da cesta — não a diferença bruta entre 1º e 8º do ranking.** Moeda candidata precisa estar significativamente mais forte que a maioria (ou todas) das outras 7, não só mais forte que a mais fraca isolada. Limiar mínimo (5, 6 ou 7 de 7) determinado empiricamente pelo backtest (Seção 5)
- [x] **Stop/take**: calibrado empiricamente pela relação entre intensidade do sinal de força e magnitude de movimento subsequente, medida apenas no período de desenvolvimento — nunca no período de validação (Seção 5)

## 10. Perguntas em aberto para fechar antes de gerar o prompt do Claude Code

- [ ] Levantar dados reais de spread por par na Exness para calibrar os limites por par (Seção 6) — isso pode ser um pequeno script de coleta antes mesmo do backtest principal
