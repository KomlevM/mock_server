# -*- coding: utf-8 -*-
"""Estimate -> часы, 8 ч/день. DECISIONS 3.6."""
import pytest

from normalization import (
    normalize_estimate, _normalize_estimate_or_unknown, UNKNOWN,
)


@pytest.mark.parametrize("raw,hours", [
    (2, 2.0), (2.5, 2.5), ("2h", 2.0), ("2ч", 2.0), ("2 час", 2.0),
    ("1,5h", 1.5), ("0.5d", 4.0), ("2d", 16.0), ("2д", 16.0),
    ("2 дня", 16.0), ("1 день", 8.0), ("3 дней", 24.0),
])
def test_normalize_estimate_units(raw, hours):
    assert normalize_estimate(raw) == hours


@pytest.mark.parametrize("raw", [None, "", "   ", "?", "abc", True, False])
def test_normalize_estimate_none(raw):
    assert normalize_estimate(raw) is None


def test_normalize_estimate_unknown_vs_none():
    assert _normalize_estimate_or_unknown(None) is None
    assert _normalize_estimate_or_unknown("") is None
    assert _normalize_estimate_or_unknown("   ") is None
    assert _normalize_estimate_or_unknown("abc") == UNKNOWN
    assert _normalize_estimate_or_unknown("2d") == 16.0