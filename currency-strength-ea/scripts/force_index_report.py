#!/usr/bin/env python3
"""Fase 2, item 6: relatório de concordância/divergência entre o Método A
(força por magnitude) e o Método C (ranking por placar de vitórias/derrotas)
— ver src/force_index.py para a definição de cada um.

Não decide se a divergência invalida o método (não é essa a instrução da
Fase 2) — só documenta onde e quanto os dois concordam, para revisão.

Uso:
    python -m scripts.force_index_report
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from src import db
from src.windows import WINDOW_VARIANTS

LARGE_DIVERGENCE_RHO = 0.5  # abaixo disso, concordância fraca entre A e C nesse timestamp


def _spearman_rho_per_row(rank_a: pd.DataFrame, rank_c: pd.DataFrame) -> pd.Series:
    """Spearman rho linha a linha entre dois DataFrames de ranking (mesmas
    colunas/índice), ignorando colunas NaN em cada linha. Fórmula fechada
    (sem laço python): rho = 1 - 6*sum(d^2) / (n*(n^2-1)), n = nº de moedas
    com rank em ambos os métodos naquela linha."""
    d2 = (rank_a - rank_c) ** 2
    valid = rank_a.notna() & rank_c.notna()
    d2 = d2.where(valid)
    n = valid.sum(axis=1)
    sum_d2 = d2.sum(axis=1, skipna=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = 1 - 6 * sum_d2 / (n * (n**2 - 1))
    rho = rho.where(n >= 3)  # rho não é informativo com menos de 3 moedas comparáveis
    return rho


def main() -> None:
    conn = db.connect(config.DB_PATH)
    lines = ["# Fase 2 — Método A vs. Método C (concordância/divergência)\n"]
    lines.append(
        "Spearman ρ linha a linha entre o ranking implícito do Método A (força por magnitude, "
        "maior = mais forte) e o Método C (placar de vitórias/derrotas nos 7 confrontos — ver "
        "`src/force_index.py`). ρ=1 → concordância total; ρ perto de 0/negativo → divergência "
        f"grande (linhas com ρ < {LARGE_DIVERGENCE_RHO} contadas à parte).\n"
    )

    per_currency_rows = []

    for variant in WINDOW_VARIANTS:
        df = pd.read_sql_query(
            "SELECT ts_utc, currency, force_a, rank_c FROM force_index WHERE variant = ?",
            conn,
            params=(variant,),
        )
        force_wide = df.pivot(index="ts_utc", columns="currency", values="force_a")
        rank_c_wide = df.pivot(index="ts_utc", columns="currency", values="rank_c")
        rank_a_wide = force_wide.rank(axis=1, ascending=False, method="average")

        rho = _spearman_rho_per_row(rank_a_wide, rank_c_wide)
        n_rows = rho.notna().sum()
        top1_a = force_wide.idxmax(axis=1)
        top1_c = rank_c_wide.idxmin(axis=1)
        top1_agree = (top1_a == top1_c).sum() / len(top1_a)

        lines.append(f"## Variante: `{variant}`\n")
        lines.append(f"- Timestamps comparados: {n_rows:,}")
        lines.append(f"- ρ médio: {rho.mean():.4f} | ρ mediano: {rho.median():.4f}")
        lines.append(
            f"- Linhas com ρ = 1.0 (concordância total): "
            f"{(rho == 1.0).sum():,} ({100 * (rho == 1.0).sum() / n_rows:.1f}%)"
        )
        lines.append(
            f"- Linhas com ρ < {LARGE_DIVERGENCE_RHO} (divergência grande): "
            f"{(rho < LARGE_DIVERGENCE_RHO).sum():,} ({100 * (rho < LARGE_DIVERGENCE_RHO).sum() / n_rows:.1f}%)"
        )
        lines.append(f"- Moeda mais forte: A e C concordam em {100 * top1_agree:.1f}% dos timestamps\n")

        mad = (rank_a_wide - rank_c_wide).abs().mean()
        for currency, value in mad.sort_values(ascending=False).items():
            per_currency_rows.append({"variant": variant, "currency": currency, "mad_rank": value})

    lines.append("## Divergência média de ranking por moeda (|rank_A - rank_C|, todas as variantes)\n")
    mad_df = pd.DataFrame(per_currency_rows).pivot(index="currency", columns="variant", values="mad_rank").round(3)
    header = "| moeda | " + " | ".join(mad_df.columns) + " |"
    sep = "|---|" + "---|" * len(mad_df.columns)
    body = "\n".join(
        f"| {currency} | " + " | ".join(f"{v:.3f}" for v in row) + " |"
        for currency, row in mad_df.iterrows()
    )
    lines.append("\n".join([header, sep, body]))
    lines.append(
        "\nValores maiores = essa moeda é a que mais muda de posição entre os dois métodos "
        "(candidata a olhar de perto se os dois forem usados para decidir entrada na Fase 3)."
    )

    out = Path("reports/force_index_a_vs_c.md")
    out.write_text("\n".join(str(x) for x in lines), encoding="utf-8")
    print(f"Relatório escrito em {out}")
    conn.close()


if __name__ == "__main__":
    main()
