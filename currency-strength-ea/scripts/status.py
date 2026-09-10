#!/usr/bin/env python3
"""Status da coleta num relance — rode você mesmo, não gasta nada.

    python -m scripts.status
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURGBP"]
END = datetime(2026, 9, 1, tzinfo=timezone.utc)  # "completo" = passou disto


def main() -> None:
    if not os.path.exists(config.DB_PATH):
        print("banco ainda não existe:", config.DB_PATH)
        return
    c = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=10)

    rows = {
        n: (mn, mx, k)
        for n, mn, mx, k in c.execute(
            "SELECT s.name, MIN(ts_utc), MAX(ts_utc), COUNT(*) "
            "FROM candles_m5 c JOIN symbols s ON s.id = c.symbol_id GROUP BY s.name"
        )
    }
    crosses = [p for p in config.PAIRS if p not in MAJORS]

    def line(group: list[str]) -> None:
        for n in group:
            if n not in rows:
                print(f"  {n}: (sem dado)")
                continue
            mn, mx, k = rows[n]
            last = datetime.fromtimestamp(mx, timezone.utc)
            tag = "completo" if last >= END else f"-> {last:%Y-%m-%d}"
            print(f"  {n}: {tag:>12}  {k:>7,}")

    print("=== MAJORS ===")
    line(MAJORS)
    print("=== CRUZADOS ===")
    line(crosses)

    total = c.execute("SELECT COUNT(*) FROM candles_m5").fetchone()[0]
    gaps = c.execute("SELECT COUNT(*) FROM data_gaps").fetchone()[0]
    done_c = sum(1 for n in crosses if n in rows and datetime.fromtimestamp(rows[n][1], timezone.utc) >= END)
    print(f"\ncandles_m5: {total:,}  | cruzados completos: {done_c}/{len(crosses)}  | data_gaps: {gaps}")

    sp = c.execute("SELECT COUNT(*), MAX(ts_utc) FROM spread_samples").fetchone()
    if sp[1]:
        age = time.time() - sp[1]
        print(f"spread_samples: {sp[0]:,}  | última há {age:.0f}s "
              f"({'ok' if age < 300 else 'ATRASADO'})")

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\").CommandLine -join '|'"],
            capture_output=True, text=True, timeout=20,
        ).stdout
        print(f"proc backfill:   {'vivo' if 'download_history_dukascopy' in out else 'PARADO'}")
        print(f"proc supervisor: {'vivo' if 'spread_sampler_supervisor' in out else 'PARADO'}")
        n_samplers = out.count('scripts.spread_sampler') - out.count('spread_sampler_supervisor')
        print(f"proc sampler:    {'vivo' if n_samplers > 0 else 'PARADO'}")
    except Exception:
        pass

    c.close()


if __name__ == "__main__":
    main()
