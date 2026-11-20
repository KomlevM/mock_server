# -*- coding: utf-8 -*-
"""FILTER_NONE_ID (-1) vs UNKNOWN_ID (0); assignee_active. DECISIONS 3.5, 3.7."""
import pytest

from normalization import (
    _match_eq, _match_in_tags, _to_bool, _is_none_id,
    UNKNOWN, UNKNOWN_ID, FILTER_NONE_ID,
)


@pytest.mark.parametrize("actual,expected", [
    (None, FILTER_NONE_ID),
    (None, "-1"),
    (None, None),
])
def test_match_eq_none_id(actual, expected):
    assert _match_eq(actual, expected) is True


def test_match_eq_none_id_does_not_match_unknown():
    """Ключевое: -1 != 0. «Нет значения» не матчит «Неизвестно»."""
    assert _match_eq(UNKNOWN, FILTER_NONE_ID) is False
    assert _match_eq(UNKNOWN, UNKNOWN_ID) is True
    assert _match_eq(None, UNKNOWN_ID) is False


def test_match_eq_status_by_id_and_canon():
    assert _match_eq("NEW", 1) is True          # канон vs id
    assert _match_eq("NEW", "NEW") is True      # канон vs канон
    assert _match_eq("NEW", 2) is False
    assert _match_eq(None, None) is False


@pytest.mark.parametrize("tags,expected,ok", [
    ([], FILTER_NONE_ID, True),
    ([], 1, False),
    (["биллинг", "срочно"], 1, True) if False else (["x"], -1, False),
    (["x"], "x", True),
    (["y"], "x", False),
])
def test_match_in_tags(tags, expected, ok):
    assert _match_in_tags(tags, expected) is ok


@pytest.mark.parametrize("v,expected", [
    (True, True), (False, False), (1, True), (0, False),
    ("true", True), ("1", True), ("yes", True), ("y", True),
    ("false", False), ("", False), ("garbage", None),
    (None, None),
])
def test_to_bool(v, expected):
    assert _to_bool(v) is expected


@pytest.mark.parametrize("v", [-1, "-1", -1.0])
def test_is_none_id_true(v):
    assert _is_none_id(v) is True


@pytest.mark.parametrize("v", [0, "0", 1, None, True, "", "x"])
def test_is_none_id_false(v):
    assert _is_none_id(v) is False