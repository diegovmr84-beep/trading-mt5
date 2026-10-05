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

-- Fase 2: índice de força por moeda (src/force_index.py). `variant` é a
-- janela de cálculo do retorno (daily/session/overlap, src/windows.py) —
-- as três convivem na mesma tabela, a escolha entre elas é da Fase 4, não
-- feita aqui. `force_a` = Método A (média simples dos retornos
-- sinalizados); `rank_c` = Método C (ranking 1=mais forte..8=mais fraco),
-- NULL quando a moeda não tinha nenhum par disponível no timestamp.
CREATE TABLE IF NOT EXISTS force_index (
    ts_utc    INTEGER NOT NULL,
    variant   TEXT NOT NULL,
    currency  TEXT NOT NULL,
    force_a   REAL,
    rank_c    REAL,
    PRIMARY KEY (ts_utc, variant, currency)
);

CREATE INDEX IF NOT EXISTS idx_force_variant_currency ON force_index (variant, currency);

-- Fase 3: eventos de sinal candidatos (src/signals.py). Um evento = ONSET de
-- sinal num par (não cada candle em que o sinal persiste). `param_set` nomeia
-- a combinação de parâmetros (k/z/horizonte/quantis/spread) — várias
-- combinações convivem na tabela para a varredura da Fase 4. `period` é
-- 'dev', 'val' ou 'embargo' segundo o corte 70/30 (src/split.py; embargo = evento cuja janela de resultado cruza o corte — fora de calibração E de validação); `spread_ok` é o
-- filtro de pares operáveis (src/spread_model.py). Nenhuma coluna aqui é
-- P&L: o resultado dos trades só existe a partir da Fase 4.
CREATE TABLE IF NOT EXISTS signal_candidates (
    param_set      TEXT NOT NULL,
    variant        TEXT NOT NULL,
    ts_utc         INTEGER NOT NULL,
    pair           TEXT NOT NULL,
    direction      INTEGER NOT NULL,   -- +1 long (compra o par), -1 short
    strong_ccy     TEXT NOT NULL,
    weak_ccy       TEXT NOT NULL,
    n_strong       INTEGER,
    n_weak         INTEGER,
    z_pair         REAL,
    force_gap      REAL,
    rank_c_strong  REAL,
    rank_c_weak    REAL,
    priority       INTEGER,
    sigma1         REAL,
    bucket         INTEGER,
    take_rel       REAL,
    stop_rel       REAL,
    session        TEXT,
    spread_rel     REAL,
    spread_ok      INTEGER,
    period         TEXT NOT NULL,
    PRIMARY KEY (param_set, variant, ts_utc, pair)
);

-- Fase 3: tabela de calibração stop/take (src/calibration.py), calibrada SÓ
-- com eventos de desenvolvimento. take_z/stop_z em unidades de
-- sigma1*sqrt(horizonte).
CREATE TABLE IF NOT EXISTS stop_take_calibration (
    param_set  TEXT NOT NULL,
    variant    TEXT NOT NULL,
    bucket     INTEGER NOT NULL,
    z_lo       REAL,
    z_hi       REAL,
    take_z     REAL,
    stop_z     REAL,
    n_events   INTEGER,
    cutoff_ts  INTEGER NOT NULL,       -- corte dev/validação usado
    PRIMARY KEY (param_set, variant, bucket)
);

-- Fase 4: trades simulados (src/backtest.py). `run`: 'dev_sweep' (as 9
-- configurações, só desenvolvimento), 'walk_forward' ou 'oos' (configuração
-- escolhida, validação). Retornos em log; net_ret = gross_ret - cost_ret.
CREATE TABLE IF NOT EXISTS backtest_trades (
    run          TEXT NOT NULL,
    config       TEXT NOT NULL,
    scenario     TEXT NOT NULL,
    period       TEXT NOT NULL,
    ts_utc       INTEGER NOT NULL,
    pair         TEXT NOT NULL,
    direction    INTEGER,
    strong_ccy   TEXT,
    weak_ccy     TEXT,
    take_rel     REAL,
    stop_rel     REAL,
    exit_reason  TEXT,
    bars_held    INTEGER,
    gross_ret    REAL,
    cost_ret     REAL,
    net_ret      REAL
);
CREATE INDEX IF NOT EXISTS idx_bt_run ON backtest_trades (run, config, scenario);

-- Fase 4: registro de abertura do período de validação. O out-of-sample só pode
-- ser aberto UMA vez; scripts/run_validation.py recusa rodar se já houver linha.
CREATE TABLE IF NOT EXISTS validation_lock (
    opened_at TEXT NOT NULL,
    config    TEXT NOT NULL,
    note      TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    # timeout / busy_timeout: espera o lock em vez de erro imediato quando
    # outro processo está escrevendo. O backfill de histórico
    # (download_history_dukascopy.py) e o spread_sampler.py rodam em paralelo,
    # os dois escrevendo neste mesmo arquivo.
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL: um escritor + leitores concorrentes sem bloquear entre si. É uma
    # propriedade persistente do arquivo (basta setar uma vez; re-setar a
    # cada conexão é inócuo).
    conn.execute("PRAGMA journal_mode = WAL;")
    # 60s: o backfill de histórico, a detecção de gaps no fim de cada par e o
    # spread_sampler disputam o lock de escrita. 30s às vezes não bastava.
    conn.execute("PRAGMA busy_timeout = 60000;")
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


def insert_spread_samples(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: tuplas (symbol_id, ts_utc, session, bid, ask, spread_points).

    Uma transação para o ciclo inteiro (os 28 pares), em vez de um commit por
    par — reduz a contenção de lock quando o backfill de histórico está
    escrevendo no mesmo arquivo em paralelo."""
    conn.executemany(
        "INSERT INTO spread_samples (symbol_id, ts_utc, session, bid, ask, spread_points) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def delete_data_gaps_for_symbol(conn: sqlite3.Connection, symbol_id: int) -> None:
    conn.execute("DELETE FROM data_gaps WHERE symbol_id = ?", (symbol_id,))
    conn.commit()


def insert_data_gap(
    conn: sqlite3.Connection, symbol_id: int, gap_start_utc: int, gap_end_utc: int, note: str = ""
) -> None:
    conn.execute(
        "INSERT INTO data_gaps (symbol_id, gap_start_utc, gap_end_utc, note) VALUES (?, ?, ?, ?)",
        (symbol_id, gap_start_utc, gap_end_utc, note),
    )
    conn.commit()


def replace_signal_candidates(
    conn: sqlite3.Connection, param_set: str, variant: str, rows: list[tuple]
) -> int:
    """Substitui TODOS os eventos de (param_set, variant) pelos `rows` dados —
    recalcular não deixa lixo da execução anterior."""
    conn.execute("DELETE FROM signal_candidates WHERE param_set = ? AND variant = ?", (param_set, variant))
    conn.executemany(
        "INSERT INTO signal_candidates (param_set, variant, ts_utc, pair, direction, strong_ccy, "
        "weak_ccy, n_strong, n_weak, z_pair, force_gap, rank_c_strong, rank_c_weak, priority, "
        "sigma1, bucket, take_rel, stop_rel, session, spread_rel, spread_ok, period) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def replace_stop_take_calibration(
    conn: sqlite3.Connection, param_set: str, variant: str, rows: list[tuple]
) -> int:
    """rows: (bucket, z_lo, z_hi, take_z, stop_z, n_events, cutoff_ts)."""
    conn.execute("DELETE FROM stop_take_calibration WHERE param_set = ? AND variant = ?", (param_set, variant))
    conn.executemany(
        "INSERT INTO stop_take_calibration (param_set, variant, bucket, z_lo, z_hi, take_z, stop_z, "
        "n_events, cutoff_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(param_set, variant, *r) for r in rows],
    )
    conn.commit()
    return len(rows)


def delete_force_index_for_variant(conn: sqlite3.Connection, variant: str) -> None:
    conn.execute("DELETE FROM force_index WHERE variant = ?", (variant,))
    conn.commit()


def insert_force_index(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (ts_utc, variant, currency, force_a, rank_c). Upsert-safe —
    recalcular uma variante e regravar não duplica nem falha."""
    conn.executemany(
        "INSERT INTO force_index (ts_utc, variant, currency, force_a, rank_c) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(ts_utc, variant, currency) DO UPDATE SET "
        "force_a=excluded.force_a, rank_c=excluded.rank_c",
        rows,
    )
    conn.commit()
    return len(rows)
