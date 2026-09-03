#!/usr/bin/env python3
"""Uso único — Opção A da Fase 1: limpar candles_m5 e data_gaps para
reconstruir o histórico só a partir da Dukascopy (o banco tinha ~1.4M
candles M5 de origem MT5, que a branch decidiu aposentar). symbols e
spread_samples são preservados.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

p = config.DB_PATH
print("arquivo:", p)
print("tamanho antes:", os.path.getsize(p) // 1024 // 1024, "MB")

conn = sqlite3.connect(p, timeout=30)
before = {
    t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for t in ("symbols", "candles_m5", "data_gaps", "spread_samples")
}
print("antes :", before)

conn.execute("DELETE FROM candles_m5")
conn.execute("DELETE FROM data_gaps")
conn.commit()
conn.execute("VACUUM")
conn.close()

conn = sqlite3.connect(p)
after = {
    t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for t in ("symbols", "candles_m5", "data_gaps", "spread_samples")
}
conn.close()
print("depois:", after)
print("tamanho depois:", os.path.getsize(p) // 1024 // 1024, "MB")
