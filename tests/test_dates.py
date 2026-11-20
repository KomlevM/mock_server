# -*- coding: utf-8 -*-
"""parse_dt: ISO / без зоны / сек / мс / dd.mm.yyyy / мусор. DECISIONS 4."""
from datetime import datetime, timezone

import pytest

from normalization import parse_dt, normalize_dt, _normalize_dt_or_unknown, UNKNOWN


def _utc(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw,expected", [
    ("2026-10-03T18:17:00Z",       _utc(2026, 10, 3, 18, 17)),
    ("2026-10-03T18:17:00+00:00",  _utc(2026, 10, 3, 18, 17)),
    ("2026-10-03T21:17:00+03:00",  _utc(2026, 10, 3, 18, 17)),  # зона учтена
    ("2026-10-03T18:17:00",        _utc(2026, 10, 3, 18, 17)),  # без зоны = UTC
    ("03.10.2026 18:17",           _utc(2026, 10, 3, 18, 17)),
    ("03.10.2026",                 _utc(2026, 10, 3)),
])
def test_parse_dt_formats(raw, expected):
    assert parse_dt(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    (1791861420,        _utc(2026, 10, 13, 3, 17)),
    (1758308640,        _utc(2025, 9, 19, 19, 4)),     # ← исправлено
    (1778613900000,     _utc(2026, 5, 12, 19, 25)),
    (1786001820000,     _utc(2026, 8, 6, 7, 37)),
    (1789646160000,     _utc(2026, 9, 17, 11, 56)),    # ← исправлено
    (1760794620000,     _utc(2025, 10, 18, 13, 37)),   # ← исправлено
])
def test_parse_dt_unix_real_values(raw, expected):
    assert parse_dt(raw) == expected


def test_parse_dt_ms_boundary_1e12():
    """DECISIONS 4: >1e12 = мс, иначе сек. Ровно 1e12 — секунды."""
    # 1e12 сек = год ~33658 — fromtimestamp упадёт -> None (не мс!)
    assert parse_dt(1_000_000_000_000) is None
    # 1e12 + 1 -> мс -> 2001-09-09
    assert parse_dt(1_000_000_000_001) == _utc(2001, 9, 9, 1, 46, 40)


@pytest.mark.parametrize("raw", [None, "", "   ", "not-a-date", "2026-13-40", [], {}])
def test_parse_dt_garbage_none(raw):
    assert parse_dt(raw) is None


@pytest.mark.parametrize("raw", [True, False])
def test_parse_dt_bool_is_none(raw):
    """bool не должен превращаться в 1970-01-01."""
    assert parse_dt(raw) is None


def test_normalize_dt_output_format():
    assert normalize_dt("2026-10-03T18:17:00Z") == "03.10.2026 18:17"
    assert normalize_dt(None) is None
    assert normalize_dt("garbage") is None


@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    ("   ", None),
    ("2026-10-03T18:17:00Z", "03.10.2026 18:17"),
    ("garbage", UNKNOWN),
    (1791861420, "13.10.2026 03:17"),
])
def test_normalize_dt_or_unknown(raw, expected):
    assert _normalize_dt_or_unknown(raw) == expected