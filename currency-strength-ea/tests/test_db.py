import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db


def test_schema_creates_all_tables(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"symbols", "candles_m5", "spread_samples", "data_gaps"} <= tables
    conn.close()


def test_upsert_symbol_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    id1 = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    id2 = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    assert id1 == id2
    count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    assert count == 1
    conn.close()


def test_insert_and_upsert_candles(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")

    rows = [(1_700_000_000, 1.1, 1.2, 1.0, 1.15, 100, 0, 2)]
    db.insert_candles(conn, sid, rows)

    stored = conn.execute("SELECT open, close FROM candles_m5 WHERE symbol_id = ?", (sid,)).fetchall()
    assert stored == [(1.1, 1.15)]

    # upsert do mesmo timestamp deve atualizar, não duplicar
    rows_updated = [(1_700_000_000, 1.1, 1.3, 1.0, 1.25, 150, 0, 3)]
    db.insert_candles(conn, sid, rows_updated)
    stored = conn.execute("SELECT close FROM candles_m5 WHERE symbol_id = ?", (sid,)).fetchall()
    assert stored == [(1.25,)]
    conn.close()


def test_insert_spread_sample_and_gap(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")

    db.insert_spread_sample(conn, sid, 1_700_000_000, "london", 1.1000, 1.1002, 0.0002)
    row = conn.execute("SELECT session, spread_points FROM spread_samples WHERE symbol_id = ?", (sid,)).fetchone()
    assert row == ("london", 0.0002)

    db.insert_data_gap(conn, sid, 1_700_000_000, 1_700_100_000, note="teste")
    gap = conn.execute("SELECT note FROM data_gaps WHERE symbol_id = ?", (sid,)).fetchone()
    assert gap == ("teste",)
    conn.close()


def test_delete_data_gaps_for_symbol(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    other_sid = db.upsert_symbol(conn, "USDJPY", "USD", "JPY")

    db.insert_data_gap(conn, sid, 1, 2, note="a")
    db.insert_data_gap(conn, sid, 3, 4, note="b")
    db.insert_data_gap(conn, other_sid, 5, 6, note="c")

    db.delete_data_gaps_for_symbol(conn, sid)

    remaining = conn.execute("SELECT symbol_id, note FROM data_gaps").fetchall()
    assert remaining == [(other_sid, "c")]
    conn.close()
