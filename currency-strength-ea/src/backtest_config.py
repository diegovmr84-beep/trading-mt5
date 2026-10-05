"""Pré-registração da Fase 4 — regras de decisão fixadas ANTES de rodar qualquer
backtest (ver o commit deste arquivo: ele precede os resultados no histórico do
git). Nada aqui pode ser alterado depois de ver resultado do período de
desenvolvimento e, muito menos, do de validação.

Os valores marcados [SUPOSIÇÃO] são escolhas minhas sem dado por trás (o
estudo manda definir, não diz o valor); estão aqui, visíveis, para revisão. O
usuário aprovou os multiplicadores de custo (1x/2x/3x) em 2026-10-05.
"""

from __future__ import annotations

from dataclasses import dataclass

# ----------------------------------------------------------------------------
# Grade de parâmetros varrida SÓ no período de desenvolvimento (Fase 4, item 2).
# Tudo o mais fica nos defaults aprovados da Fase 3 (z_crit=2.0, horizonte=36,
# q_take=0.5, q_stop=0.75, 4 faixas de intensidade, spread 0.75/0.25).
# ----------------------------------------------------------------------------
VARIANTS = ("daily", "session", "overlap")
K_MIN_GRID = (5, 6, 7)
N_CONFIGS = len(VARIANTS) * len(K_MIN_GRID)  # 9

Z_CRIT = 2.0
HORIZON = 36
MAX_SPREAD_TO_TAKE = 0.25
GAP_THRESHOLD_S = 7200


def param_set_name(k: int) -> str:
    """Nome do param_set gravado por scripts/generate_signals.py com os defaults."""
    return f"k{k}_z{Z_CRIT}_H{HORIZON}_qt0.5_qs0.75_sq0.75_sf{MAX_SPREAD_TO_TAKE}"


# ----------------------------------------------------------------------------
# Cenários de custo (Fase 4, item 8). Aprovados pelo usuário: 1x / 2x / 3x o
# spread medido. O spread da Trial é fixo (piso), então os multiplicadores são
# suposições, não medidas. O custo de ida-e-volta é UM spread (compra no ask,
# vende no bid). Cenário pessimista soma slippage = 0,5 spread [SUPOSIÇÃO].
# O filtro de spread (Fase 3) é reaplicado em cada cenário com o spread escalado.
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Scenario:
    name: str
    spread_mult: float
    slippage_spread_frac: float = 0.0

    @property
    def cost_mult(self) -> float:
        return self.spread_mult + self.slippage_spread_frac


SCENARIOS = {
    "otimista": Scenario("otimista", 1.0),
    "realista": Scenario("realista", 2.0),
    "pessimista": Scenario("pessimista", 3.0, 0.5),
}
PRIMARY_SCENARIO = "realista"   # seleção e veredicto usam este; os outros são sensibilidade

# ----------------------------------------------------------------------------
# Simulação de trade
# ----------------------------------------------------------------------------
# Entrada na abertura do candle do sinal; stop/take nos níveis calibrados na Fase
# 3; saída por tempo no fechamento do último candle do horizonte (ou do último
# candle antes de um gap). Se stop e take caem no MESMO candle, assume-se que o
# stop foi atingido primeiro (conservador — não há dado intra-candle).

# ----------------------------------------------------------------------------
# Critérios do veredicto (três cumulativos — Fase 4, itens 3, 4, 5)
# ----------------------------------------------------------------------------
ALPHA = 0.05
# Contagem de testes para Bonferroni (item 3): camada externa = 9 configurações da
# grade; camada interna = até 7 comparações par-a-par por moeda candidata dentro
# do critério de entrada (Seção 4 do estudo). Contagem explícita e conservadora:
M_OUTER = N_CONFIGS          # 9
M_INNER = 7
M_TESTS = M_OUTER * M_INNER  # 63
ALPHA_BONFERRONI = ALPHA / M_TESTS

N_MIN_TRADES = 100           # [SUPOSIÇÃO] abaixo disso o resultado é "preliminar"
MIN_EFFECT_R = 0.10          # [SUPOSIÇÃO] expectativa líquida mínima = 0,10 R (R = stop médio)
OOS_ALPHA = 0.05             # configuração única pré-especificada no OOS: teste unilateral (média > 0)

# Regra de seleção no desenvolvimento (fixada antes de rodar): entre as
# configurações com >= N_MIN_TRADES, a de maior estatística t (robusta a
# cluster por dia) da expectativa líquida no cenário primário. Se nenhuma
# atinge N_MIN_TRADES, escolhe-se a de maior t e o resultado sai "preliminar".

# Walk-forward (item 6): treina 6 meses, testa o mês seguinte, desliza 1 mês,
# só dentro do período de desenvolvimento. A cada dobra reescolhe a configuração
# (mesma regra acima) e recalibra stop/take só com eventos de treino.
WF_TRAIN_MONTHS = 6
WF_TEST_MONTHS = 1
WF_MIN_TRAIN_TRADES = 20     # dobras de treino com menos trades que isso não escolhem configuração

# Veredicto:
#   "validado"     — TODOS: (dev) significativo com Bonferroni, n >= N_MIN, efeito >= MIN_EFFECT_R;
#                    (OOS, config escolhida, cenário primário) média líquida > 0 com p unilateral
#                    < OOS_ALPHA, n >= N_MIN, efeito >= MIN_EFFECT_R; walk-forward com média > 0.
#   "não validado" — expectativa líquida <= 0 no OOS (cenário primário) OU <= 0 no
#                    desenvolvimento da configuração escolhida (sem edge nem in-sample).
#   "preliminar"   — todo o resto (sinal positivo, mas falha amostra mínima, significância,
#                    efeito mínimo ou walk-forward).
# Fase 5 só começa com "validado" E aprovação explícita do usuário.
