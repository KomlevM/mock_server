# -*- coding: utf-8 -*-
"""Статусы/приоритеты: алиасы из DECISIONS 3.2/3.3, int-id, -1/0. """
import pytest

from normalization import (
    normalize_status, normalize_priority, status_id, priority_id,
    status_label, priority_label, _status_from_filter, _priority_from_filter,
    UNKNOWN, UNKNOWN_ID, FILTER_NONE_ID,
    STATUS_IDS, PRIORITY_IDS,
)

# Реальные сырые значения из дампа + все алиасы из DECISIONS 3.2.
@pytest.mark.parametrize("raw,canon", [
    ("new", "NEW"), ("open", "NEW"), ("tod", "NEW"), ("todo", "NEW"), ("ждут", "NEW"),
    ("in_progress", "IN_PROGRESS"), ("in-progress", "IN_PROGRESS"),
    ("inproges", "IN_PROGRESS"), ("doing", "IN_PROGRESS"), ("в работе", "IN_PROGRESS"),
    ("reviw", "CODE_REVIEW"), ("review", "CODE_REVIEW"), ("code_rviw", "CODE_REVIEW"),
    ("blocked", "BLOCKED"),
    ("hold", "HOLD"),
    ("done", "DONE"), ("resolvd", "DONE"), ("closed", "DONE"),
    ("canceled", "DONE"), ("caneld", "DONE"), ("cancelled", "DONE"),  # DECISIONS 12: TBD
])
def test_normalize_status_aliases(raw, canon):
    assert normalize_status(raw) == canon


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_normalize_status_empty_is_none(raw):
    assert normalize_status(raw) is None


def test_normalize_status_unknown():
    assert normalize_status("что-то непонятное") == UNKNOWN


def test_normalize_status_case_and_spaces():
    assert normalize_status("  IN_PROGRESS  ") == "IN_PROGRESS"
    assert normalize_status("In Progress") == UNKNOWN  # пробел внутри не алиас


@pytest.mark.parametrize("raw,canon", [
    ("0", "P0"), ("p0", "P0"), ("крит", "P0"), ("critical", "P0"),
    ("1", "P1"), ("p1", "P1"), ("high", "P1"), ("высокий", "P1"),
    ("2", "P2"), ("normal", "P2"), ("medium", "P2"), ("средний", "P2"),
    ("3", "P3"), ("p3", "P3"), ("low", "P3"), ("низкий", "P3"),
])
def test_normalize_priority_aliases(raw, canon):
    assert normalize_priority(raw) == canon


def test_normalize_priority_unknown():
    assert normalize_priority("срочно!!!") == UNKNOWN


def test_ids_are_stable():
    """DECISIONS 3.5: id стабильны, не менять без миграции фронта."""
    assert STATUS_IDS == {"NEW": 1, "IN_PROGRESS": 2, "CODE_REVIEW": 3,
                          "BLOCKED": 4, "HOLD": 5, "DONE": 6}
    assert PRIORITY_IDS == {"P0": 1, "P1": 2, "P2": 3, "P3": 4}


@pytest.mark.parametrize("canon,expected_id", [
    ("NEW", 1), ("DONE", 6), (UNKNOWN, UNKNOWN_ID), (None, UNKNOWN_ID),
])
def test_status_id(canon, expected_id):
    assert status_id(canon) == expected_id


@pytest.mark.parametrize("canon,label", [
    ("NEW", "Новый"), ("DONE", "Готово"), (UNKNOWN, UNKNOWN), (None, None),
])
def test_status_label(canon, label):
    assert status_label(canon) == label


def test_priority_label():
    assert priority_label("P0") == "Крит"
    assert priority_label(UNKNOWN) == UNKNOWN


@pytest.mark.parametrize("v,expected", [
    (1, "NEW"), ("2", "IN_PROGRESS"), ("new", "NEW"), ("open", "NEW"),
    (0, UNKNOWN), (UNKNOWN_ID, UNKNOWN),
    (-1, FILTER_NONE_ID), ("-1", FILTER_NONE_ID),
    (999, None),
])
def test_status_from_filter(v, expected):
    assert _status_from_filter(v) == expected


@pytest.mark.parametrize("v,expected", [
    (1, "P0"), (3, "P2"), ("p0", "P0"),
    (0, UNKNOWN), (-1, FILTER_NONE_ID), (999, None),
])
def test_priority_from_filter(v, expected):
    assert _priority_from_filter(v) == expected