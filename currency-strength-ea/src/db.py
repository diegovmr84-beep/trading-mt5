"""Schema e acesso ao SQLite do Currency Strength EA.

Duas fontes de dado são armazenadas separadamente, propositalmente:

- `candles_m5`: histórico de candles M5 (2020+), baixado uma vez via
  `scripts/download_history.py`. Usado no cálculo do índice de força
  (Fase 2 em diante).
- `spread_samples`: amostras de spread AO VIVO (bid/ask reais no momento),
  coletadas continuamente via `scripts/spread_sampler.py`. O campo
  `spread` que o MT5 retorna junto com candles históricos não é uma fonte
  confiável de spread histórico real (depende da corretora armazenar isso
  corretamente para o histórico, o que não é garantido) — por isso o
  levantamento de spread da Seção 6 do estudo é feito por amostragem ao
  vivo, não a partir do candle histórico.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    base_currency   TEXT NOT NULL,
    quote_currency  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candles_m5 (
    symbol_id     INTEGER NOT NULL REFERENCES symbols(id),
    ts_utc        INTEGER NOT NULL,  -- epoch seconds UTC, abertura do candle
    open          REAL NOT NULL,
    high          REAL NOT NULL,
    low           REAL NOT NULL,
    close         REAL NOT NULL,
    tick_volume   INTEGER NOT NULL,
    real_volume   INTEGER NOT NULL DEFAULT 0,
    broker_spread INTEGER,  -- spread (pontos) reportado pelo MT5 no candle; ver aviso acima
    PRIMARY KEY (symbol_id, ts_utc)
);

CREATE INDEX IF NOT EXISTS idx_candles_ts ON candles_m5 (ts_utc);

CREATE TABLE IF NOT EXISTS spread_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id     INTEGER NOT NULL REFERENCES symbols(id),
    ts_utc        INTEGER NOT NULL,  -- epoch seconds UTC do momento da amostra
    session       TEXT NOT NULL,     -- ver src/sessions.py
    bid           REAL NOT NULL,
    ask           REAL NOT NULL,
    spread_points REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_spread_symbol_session ON spread_samples (symbol_id, session);

CREATE TABLE IF NOT EXISTS data_gaps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id     INTEGER NOT NULL REFERENCES symbols(id),
    gap_start_utc INTEGER NOT NULL,
    gap_end_utc   INTEGER NOT NULL,
    note          TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    return conn


def upsert_symbol(conn: sqlite3.Connection, name: str, base: str, quote: str) -> int:
    conn.execute(
        "INSERT INTO symbols (name, base_currency, quote_currency) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET base_currency=excluded.base_currency, "
        "quote_currency=excluded.quote_currency",
        (name, base, quote),
    )
    row = conn.execute("SELECT id FROM symbols WHERE name = ?", (name,)).fetchone()
    return row[0]


def insert_candles(conn: sqlite3.Connection, symbol_id: int, rows: list[tuple]) -> int:
    """rows: lista de tuplas (ts_utc, open, high, low, close, tick_volume, real_volume, broker_spread)."""
    conn.executemany(
        "INSERT INTO candles_m5 "
        "(symbol_id, ts_utc, open, high, low, close, tick_volume, real_volume, broker_spread) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(symbol_id, ts_utc) DO UPDATE SET "
        "open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, "
        "tick_volume=excluded.tick_volume, real_volume=excluded.real_volume, "
        "broker_spread=excluded.broker_spread",
        [(symbol_id, *row) for row in rows],
    )
    conn.commit()
    return len(rows)


def insert_spread_sample(
    conn: sqlite3.Connection,
    symbol_id: int,
    ts_utc: int,
    session: str,
    bid: float,
    ask: float,
    spread_points: float,
) -> None:
    conn.execute(
        "INSERT INTO spread_samples (symbol_id, ts_utc, session, bid, ask, spread_points) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (symbol_id, ts_utc, session, bid, ask, spread_points),
    )
    conn.commit()


def insert_data_gap(
    conn: sqlite3.Connection, symbol_id: int, gap_start_utc: int, gap_end_utc: int, note: str = ""
) -> None:
    conn.execute(
        "INSERT INTO data_gaps (symbol_id, gap_start_utc, gap_end_utc, note) VALUES (?, ?, ?, ?)",
        (symbol_id, gap_start_utc, gap_end_utc, note),
    )
    conn.commit()
