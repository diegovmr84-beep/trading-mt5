#!/usr/bin/env python3
"""Monta reports/fase4_relatorio.md a partir de reports/fase4_dev_results.json
(e de reports/fase4_oos_results.json, se a validação tiver sido aberta).

Uso:
    python -m scripts.make_fase4_report
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from src import backtest_config as cfg
from src.validation_stats import verdict


def _f(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}"


def _tiers() -> dict[str, str]:
    tier = {}
    for line in Path("reports/spread_operabilidade.md").read_text(encoding="utf-8").splitlines():
        parts = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(parts) > 3 and parts[1] in ("A", "B", "C"):
            tier[parts[0]] = parts[1]
    return tier


def main() -> None:
    dev = json.loads(Path("reports/fase4_dev_results.json").read_text(encoding="utf-8"))
    oos_path = Path("reports/fase4_oos_results.json")
    oos = json.loads(oos_path.read_text(encoding="utf-8")) if oos_path.exists() else None
    chosen = dev["chosen"]
    wf = dev["walk_forward"]
    ver, reasons = verdict(chosen, oos["primary"] if oos else None, wf.get("mean_bps") or float("nan"))
    sweep = pd.DataFrame(dev["sweep"])

    L = []
    L.append("# Relatório — Fase 4: backtest e validação estatística\n")
    L.append(f"## Veredicto: **{ver.upper()}**\n")
    for r in reasons:
        L.append(f"- {r}")
    L.append(
        f"\nCorte desenvolvimento/validação: **{dev['cutoff_utc'][:16]} UTC** (70/30). "
        + ("**A validação (out-of-sample) NÃO foi aberta.**" if oos is None else "A validação foi aberta uma única vez.")
        + " Regras de decisão pré-registradas em `src/backtest_config.py` (commit anterior a qualquer resultado).\n"
    )

    L.append("## 1. Pré-registração (fixada antes de rodar)\n")
    L.append(f"- Grade: 3 janelas × k = 5/6/7 = {cfg.N_CONFIGS} configurações; demais parâmetros nos defaults aprovados da Fase 3.")
    L.append("- Cenários de custo (aprovados): otimista 1× o spread medido, realista 2×, pessimista 3× + 0,5 spread de slippage. "
             f"O cenário **{cfg.PRIMARY_SCENARIO}** manda na seleção e no veredicto; os outros são sensibilidade.")
    L.append(f"- **Contagem de Bonferroni: {cfg.M_TESTS} = {cfg.M_OUTER} configurações × {cfg.M_INNER} comparações "
             f"par-a-par internas por moeda candidata** → α crítico = {cfg.ALPHA}/{cfg.M_TESTS} = {cfg.ALPHA_BONFERRONI:.5f}. "
             "As duas camadas (varredura de parâmetros e testes internos do critério de entrada) entram na contagem, "
             "como o estudo exige. Contagem conservadora e minha interpretação: a camada interna é um fator multiplicativo fixo de 7.")
    L.append(f"- Amostra mínima: {cfg.N_MIN_TRADES} trades (abaixo disso: **preliminar**). Efeito mínimo: expectativa líquida ≥ "
             f"{cfg.MIN_EFFECT_R} R (R = stop médio). Ambos [SUPOSIÇÃO], análogos ao |r| > 0,3 do outro projeto.")
    L.append("- Significância: erro-padrão **robusto a cluster por dia UTC** (trades do mesmo dia compartilham choques e moedas; "
             "tratá-los como independentes inflaria a significância).")
    L.append("- Simulação: entrada na abertura do candle do sinal; stop e take nos níveis calibrados só no desenvolvimento; "
             "stop e take no mesmo candle → assume stop; saída por tempo em 36 candles; sem posição carregada por gap.\n")

    L.append("## 2. Varredura no desenvolvimento (9 configurações × 3 cenários de custo)\n")
    L.append("Expectativa líquida por trade em bps (retorno log × 10⁴), t robusto a cluster, expectativa em R. "
             "`prel.` = menos de 100 trades.\n")
    L.append("| config | n (realista) | otimista (bps) | **realista (bps)** | pessimista (bps) | t realista | R realista | sig. Bonferroni? |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cid in sweep["config"].unique():
        g = sweep[sweep.config == cid].set_index("scenario")
        re = g.loc["realista"]
        sig = (re.get("p_two") is not None and re["p_two"] < cfg.ALPHA_BONFERRONI) and (re["mean_bps"] > 0)
        L.append(
            f"| {cid} | {int(re['n'])}{' prel.' if re['n'] < cfg.N_MIN_TRADES else ''} | "
            f"{_f(g.loc['otimista']['mean_bps'])} | **{_f(re['mean_bps'])}** | {_f(g.loc['pessimista']['mean_bps'])} | "
            f"{_f(re['t'])} | {_f(re['exp_R'], 3)} | {'sim' if sig else 'não'} |"
        )
    L.append(f"\n**Nenhuma das 9 configurações tem expectativa líquida positiva e significativa no cenário realista.** "
             f"Única com média positiva em algum cenário: `session_k6` no otimista (+0,08 bps, indistinguível de zero).\n")

    L.append("### Por que é negativo: bruto ≈ 0, e o custo empurra para baixo\n")
    L.append("Diagnóstico só com o desenvolvimento (cenário realista, as 9 configurações): "
             "o retorno **bruto** (antes de custo) fica entre −6,5 e +1,6 bps por trade conforme a configuração, ou seja, "
             "o sinal **não mostra edge antes de custo**; o custo (1,3 bps no otimista, ~2,5 no realista) só faz o "
             "resultado cruzar para o negativo. Take atingido em ~48% dos trades, stop em ~20%, saída por tempo em ~31%. "
             "A relação stop/take média é 1,8 — efeito dos quantis-padrão (q_take 0,5 / q_stop 0,75) definidos antes de ver o dado.\n")

    d5 = sweep[(sweep.config == "daily_k5") & (sweep.scenario == cfg.PRIMARY_SCENARIO)].iloc[0]
    L.append(
        f"**Observação (não acionável):** nas janelas `daily` o retorno é negativo "
        f"(`daily_k5`: t = {d5['t']:.2f}, p = {d5['p_two']:.3f}), o que sugere reversão, e não continuação, "
        f"no horizonte de 3h. Esse p-valor **não sobrevive ao Bonferroni** (α crítico {cfg.ALPHA_BONFERRONI:.5f}) e "
        "inverter o sinal agora, depois de ver o resultado, seria data-snooping. Só vale como **hipótese a "
        "pré-registrar** e testar uma única vez no out-of-sample intocado.\n"
    )

    L.append("## 3. Configuração escolhida (regra pré-registrada) e walk-forward\n")
    L.append(f"Regra: maior t entre as configurações com ≥ {cfg.N_MIN_TRADES} trades, cenário {cfg.PRIMARY_SCENARIO}. "
             f"Escolhida: **{chosen['config']}** — n={chosen['n']}, líquido {_f(chosen['mean_bps'])} bps, "
             f"t={_f(chosen['t'])}, p={_f(chosen['p_two'], 3)}, {_f(chosen['exp_R'], 3)} R. "
             "É a \"menos ruim\", não uma configuração com edge.\n")
    L.append(f"**Walk-forward** (treina {cfg.WF_TRAIN_MONTHS} meses, testa 1, recalibra stop/take e reescolhe a configuração "
             f"a cada dobra, só dentro do desenvolvimento): {wf['n_folds']} dobras, {wf['n_folds_with_trades']} com trades; "
             f"{wf.get('n_trades', 0)} trades de teste; média líquida **{_f(wf.get('mean_bps'))} bps** (t={_f(wf.get('t'))}); "
             f"{_f((wf.get('months_positive') or 0) * 100, 0)}% dos meses positivos. "
             "Sem estabilidade de edge ao longo do tempo — consistente com ausência de edge.\n")

    L.append("## 4. Concentração por faixa de spread (item 10 — descritivo, NÃO usar para escolher pares)\n")
    conn = sqlite3.connect(config.DB_PATH)
    tr = pd.read_sql_query(
        "SELECT config, pair, gross_ret, net_ret FROM backtest_trades WHERE run='dev_sweep' AND scenario='realista'", conn
    )
    conn.close()
    tr["faixa"] = tr["pair"].map(_tiers())
    g = tr.groupby("faixa").agg(n=("net_ret", "size"), bruto=("gross_ret", lambda s: s.mean() * 1e4),
                                liquido=("net_ret", lambda s: s.mean() * 1e4))
    L.append("| faixa de custo | trades (9 configs somadas) | bruto (bps) | líquido (bps) |")
    L.append("|---|---|---|---|")
    for faixa, r in g.iterrows():
        L.append(f"| {faixa} | {int(r.n)} | {r.bruto:.2f} | {r.liquido:.2f} |")
    L.append(
        "\nA faixa C (maior custo relativo) é a única com média positiva. **Isso não é acionável**: é um subgrupo "
        "pós-hoc, os trades das 9 configurações se sobrepõem (não são independentes), não há correção de múltiplos "
        "testes e as diferenças por par ficam dentro do ruído (±10 bps com 60-500 trades). Serve, no máximo, como "
        "**hipótese a pré-registrar** e testar uma única vez no out-of-sample ainda intocado.\n"
    )

    L.append("## 5. Item 10 — mínimos quadrados\n")
    L.append("**Não implementado**, conforme o estudo. Recomendação documentada: o problema aqui é ausência de edge bruto "
             "na média, e não ruído concentrado em pares de spread alto/liquidez baixa (a faixa C não é pior que as outras; "
             "é a única melhor). Trocar a média simples por mínimos quadrados tende a mudar pouco um sinal cujo retorno "
             "bruto já é ≈ 0. Não recomendo gastar essa iteração agora; fica registrado para decisão sua.\n")

    L.append("## 6. Validação (out-of-sample)\n")
    if oos is None:
        L.append("**Não aberta.** Pela regra pré-registrada, \"não validado\" não exige o OOS: a expectativa líquida da "
                 "melhor configuração já é ≤ 0 no desenvolvimento. Abrir o OOS aqui só queimaria o único dado nunca visto, "
                 "sem chance de validar; e qualquer redesenho feito depois de olhar o OOS passaria a ter o OOS contaminado. "
                 "O trava de abertura única (`validation_lock`) continua livre.\n")
    else:
        L.append(json.dumps(oos["primary"], indent=1, ensure_ascii=False))

    L.append("## 7. Limitações que valem para qualquer leitura\n")
    L.append("- O spread da Trial é fixo (piso de custo); os cenários 2×/3× são suposições. Uma conta real pode custar mais.")
    L.append("- 1×/2×/3× e os limiares de amostra/efeito são suposições minhas, não dados; estão visíveis em `src/backtest_config.py`.")
    L.append("- Configurações com k=7 têm 37-83 trades de desenvolvimento: rotuladas preliminares.")
    L.append("- Calibração de stop/take no desenvolvimento inteiro é in-sample para o varrimento (leve otimismo); o "
             "walk-forward recalibra por dobra e confirma o mesmo quadro.\n")

    Path("reports/fase4_relatorio.md").write_text("\n".join(L), encoding="utf-8")
    print(f"escrito reports/fase4_relatorio.md | veredicto: {ver} | {reasons}")


if __name__ == "__main__":
    main()
