"""Pré-registração da Fase 4b (redesenho v2) — fixada ANTES de abrir o out-of-sample.

Contexto: a v1 (continuação com stop/take de 3h) terminou "NÃO VALIDADA"
(reports/fase4_relatorio.md): retorno bruto ≈ 0 em todas as 9 configurações. O
estudo de eventos exploratório, só no desenvolvimento
(reports/fase4b_event_study_dev.md, 72 células), mostrou UM padrão coerente: nas
janelas `daily`, o preço REVERTE depois do sinal, com efeito crescendo com o
horizonte e com a força do sinal (k5 → k6 → k7: −34, −45, −100 bps em 24h).
Nenhuma célula sobrevive a Bonferroni (p ≈ 0,015 nas 72 testadas), o efeito é
concentrado em AUDJPY/NZDJPY (34-42% e 16-22% dos eventos) e fraco em 2021
(reports/fase4b_robustez_daily_dev.md).

Como a hipótese nasceu destes dados e foi escolhida entre 72 células, o
desenvolvimento NÃO pode confirmá-la (viés de seleção). Só o out-of-sample
intocado pode — e uma única vez. Nada abaixo pode ser alterado depois de abrir
o OOS; o commit deste arquivo precede qualquer resultado de validação.

Valores [SUPOSIÇÃO] são escolhas minhas sem dado por trás.
"""

from __future__ import annotations

HYPOTHESIS_H1 = (
    "H1: sinais da janela `daily` com k_min = 5 (z_crit = 2,0, demais parâmetros da Fase 3) "
    "são seguidos de reversão em 24h. Operar CONTRA o sinal (fade), entrada na abertura do "
    "candle do sinal e saída por tempo no fechamento do 288º candle M5 (24h) — sem stop/take —, "
    "tem expectativa líquida POSITIVA depois do custo do cenário realista (2x o spread medido)."
)

VARIANT = "daily"
K_PRIMARY = 5          # hipótese primária
K_SECONDARY = 6        # só descritivo (dose-resposta); não entra na decisão
HORIZON_CANDLES = 288  # 24h de candles M5
PRIMARY_SCENARIO = "realista"   # cenários de custo: os mesmos da v1 (1x / 2x / 3x+slippage)

# Filtros: apenas exclusão do rollover (17h de NY ±1h). Sem filtro spread-vs-take: não há
# take nesta versão, e o spread medido (<= ~3 bps) é pequeno frente ao movimento de 24h.

# --- Critérios do veredicto (um único teste pré-especificado no OOS) -----------------
OOS_ALPHA = 0.05            # unilateral (média líquida > 0), erro-padrão robusto a cluster por dia
N_MIN_TRADES = 100          # abaixo disso: "preliminar"
MIN_EFFECT_BPS = 5.0        # [SUPOSIÇÃO] média líquida >= 5 bps (~2x o custo realista de ~2,5 bps)
REQUIRE_LEAVE_TOP_PAIR_OUT_POSITIVE = True   # concentração: tirando o par mais frequente, média líquida segue > 0
REQUIRE_BOTH_HALVES_POSITIVE = True          # estabilidade: as duas metades (no tempo) do OOS com média líquida > 0

# Veredito:
#   "validado"     — TODOS: p unilateral < OOS_ALPHA, n >= N_MIN_TRADES, média líquida >= MIN_EFFECT_BPS,
#                    leave-top-pair-out > 0, ambas as metades > 0 (cenário realista).
#   "não validado" — média líquida <= 0 no cenário realista.
#   "preliminar"   — todo o resto (positivo, mas falha amostra, significância, efeito, concentração ou estabilidade).
#
# Contabilidade honesta de múltiplos testes: a hipótese foi escolhida entre 72 células + 2 checagens de
# robustez no desenvolvimento; isso invalida o desenvolvimento como confirmação, mas NÃO o OOS, que
# recebe UM teste pré-especificado (m = 1). Mesmo "validado" aqui = 1 teste com p < 0,05 numa
# hipótese de evidência prévia fraca; a decisão de seguir para a Fase 5 continua sendo do usuário.
#
# O OOS só pode ser aberto uma vez (tabela `validation_lock`). Se for aberto e falhar, a família de
# estratégias "força relativa por janela" fica sem OOS para qualquer redesenho futuro.
