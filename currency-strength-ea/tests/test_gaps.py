import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.gaps import detect_and_log_gaps

FIVE_MIN = 300


def test_no_gap_for_consecutive_m5_candles(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    rows = [(1_700_000_000 + i * FIVE_MIN,) for i in range(10)]

    found = detect_and_log_gaps(conn, sid, rows)

    assert found == 0
    conn.close()


def test_weekend_gap_under_three_days_not_flagged(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    # ~2.5 dias, gap normal de fim de semana
    rows = [(1_700_000_000,), (1_700_000_000 + int(2.5 * 86400),)]

    found = detect_and_log_gaps(conn, sid, rows)

    assert found == 0
    conn.close()


def test_gap_over_three_days_is_flagged_and_logged(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    sid = db.upsert_symbol(conn, "EURUSD", "EUR", "USD")
    rows = [(1_700_000_000,), (1_700_000_000 + 4 * 86400,)]

    found = detect_and_log_gaps(conn, sid, rows)

    assert found == 1
    stored = conn.execute("SELECT gap_start_utc, gap_end_utc FROM data_gaps WHERE symbol_id = ?", (sid,)).fetchall()
    assert stored == [(1_700_000_000, 1_700_000_000 + 4 * 86400)]
    conn.close()
