#!/usr/bin/env python3
"""Fase 1, item 3: agrega as amostras de spread coletadas por
scripts/spread_sampler.py num relatório por par/sessão (CSV + Markdown).

Não inventa número para par sem amostra suficiente — reporta explicitamente
como "dado insuficiente" em vez de omitir ou estimar.

Uso:
    python -m scripts.spread_report --min-samples 200
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db

SESSIONS = ["tokyo", "london", "ny", "london_ny_overlap", "other"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-samples", type=int, default=200, help="amostras mínimas por par/sessão para reportar número (default: 200)")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent / "reports"))
    args = parser.parse_args()

    conn = db.connect(config.DB_PATH)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_out = []
    for (symbol_name,) in conn.execute("SELECT name FROM symbols ORDER BY name"):
        symbol_id = conn.execute("SELECT id FROM symbols WHERE name = ?", (symbol_name,)).fetchone()[0]
        for session in SESSIONS:
            samples = [
                r[0]
                for r in conn.execute(
                    "SELECT spread_points FROM spread_samples WHERE symbol_id = ? AND session = ?",
                    (symbol_id, session),
                )
            ]
            if len(samples) < args.min_samples:
                rows_out.append(
                    {
                        "par": symbol_name,
                        "sessao": session,
                        "n_amostras": len(samples),
                        "spread_medio": "DADO INSUFICIENTE",
                        "spread_mediano": "DADO INSUFICIENTE",
                        "spread_maximo": "DADO INSUFICIENTE",
                    }
                )
                continue
            rows_out.append(
                {
                    "par": symbol_name,
                    "sessao": session,
                    "n_amostras": len(samples),
                    "spread_medio": round(statistics.mean(samples), 5),
                    "spread_mediano": round(statistics.median(samples), 5),
                    "spread_maximo": round(max(samples), 5),
                }
            )

    csv_path = out_dir / "spread_por_par_sessao.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()) if rows_out else [])
        writer.writeheader()
        writer.writerows(rows_out)

    md_path = out_dir / "spread_por_par_sessao.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Spread por par e sessão\n\n")
        f.write(f"Amostras mínimas para reportar número: {args.min_samples}\n\n")
        f.write("| Par | Sessão | N amostras | Spread médio | Spread mediano | Spread máximo |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in rows_out:
            f.write(
                f"| {row['par']} | {row['sessao']} | {row['n_amostras']} | "
                f"{row['spread_medio']} | {row['spread_mediano']} | {row['spread_maximo']} |\n"
            )

    conn.close()
    print(f"Relatório escrito em:\n  {csv_path}\n  {md_path}")


if __name__ == "__main__":
    main()
