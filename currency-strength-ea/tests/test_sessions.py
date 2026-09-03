import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sessions import classify_session


def _dt(hour: int) -> datetime:
    return datetime(2024, 1, 15, hour, 0, 0, tzinfo=timezone.utc)


def test_tokyo_session():
    assert classify_session(_dt(2)) == "tokyo"


def test_london_session():
    assert classify_session(_dt(9)) == "london"


def test_overlap_takes_priority_over_london_and_ny():
    assert classify_session(_dt(14)) == "london_ny_overlap"


def test_ny_session_outside_overlap():
    assert classify_session(_dt(20)) == "ny"


def test_other_outside_known_windows():
    assert classify_session(_dt(23)) == "other"


def test_naive_datetime_treated_as_utc():
    naive = datetime(2024, 1, 15, 2, 0, 0)
    assert classify_session(naive) == "tokyo"
