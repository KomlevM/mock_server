# -*- coding: utf-8 -*-
"""overdue / due_soon / date_error. DECISIONS 4, 5.1."""
import pytest

from normalization import (
    _is_overdue, _is_due_soon, _is_due_date_error,
    _is_no_active_assignee, _is_no_assignee,
)


def _t(status=None, all_data=None, assignee=None, assignee_active=None):
    return {"status": status, "all_data": all_data or {},
            "assignee": assignee, "assignee_active": assignee_active}


def _due_task(due, status="IN_PROGRESS"):
    return _t(status=status, all_data={"due": due, "created": "2026-01-01T00:00:00Z"})


def test_overdue_true(now):
    assert _is_overdue(_due_task("2026-11-01T00:00:00Z"), now) is True


def test_overdue_done_excluded(now):
    """DECISIONS 4/5.1: DONE не просрочен."""
    assert _is_overdue(_due_task("2026-11-01T00:00:00Z", status="DONE"), now) is False


def test_overdue_no_due(now):
    assert _is_overdue(_t(status="NEW"), now) is False


def test_overdue_due_uses_due_ts_fallback(now):
    """Задача 44: all_data.due=null, due_ts=1791861420 (=13.10.2026) -> overdue на now=20.11."""
    raw = {"due": None, "due_ts": 1791861420, "created": "2026-10-03T18:17:00Z"}
    assert _is_overdue(_t(status="NEW", all_data=raw), now) is True


@pytest.mark.parametrize("due,expected", [
    ("2026-11-20T12:00:00Z", True),   # ровно сейчас — due
    ("2026-11-20T12:00:01Z", True),
    ("2026-11-27T12:00:00Z", True),   # ровно N=7 дней
    ("2026-11-27T12:00:01Z", False),  # N+1 сек
    ("2026-11-19T12:00:00Z", False),  # просрочено — не due_soon
])
def test_due_soon_boundaries(now, due, expected):
    assert _is_due_soon(_t(all_data={"due": due}), now, 7) is expected


def test_due_soon_done_not_excluded(now):
    """DECISIONS 5.1 не упоминает статус для due_soon — текущее поведение: DONE попадает."""
    t = _t(status="DONE", all_data={"due": "2026-11-22T00:00:00Z"})
    assert _is_due_soon(t, now, 7) is True  # xfail при смене решения


def test_due_date_error_true(now):
    raw = {"due": "2026-01-01T00:00:00Z", "created": "2026-02-01T00:00:00Z"}
    assert _is_due_date_error(_t(all_data=raw)) is True


def test_due_date_error_false_equal_or_after(now):
    raw = {"due": "2026-02-01T00:00:00Z", "created": "2026-02-01T00:00:00Z"}
    assert _is_due_date_error(_t(all_data=raw)) is False


def test_due_date_error_false_if_missing(now):
    assert _is_due_date_error(_t(all_data={"due": "2026-01-01T00:00:00Z"})) is False
    assert _is_due_date_error(_t(all_data={"created": "2026-01-01T00:00:00Z"})) is False


@pytest.mark.parametrize("assignee,active,expected", [
    (None, None, True),
    ("И. Петров", False, True),    # нет активного
    ("И. Петров", True, False),
])
def test_no_active_assignee(assignee, active, expected):
    assert _is_no_active_assignee(
        _t(assignee=assignee, assignee_active=active)) is expected


def test_no_assignee_unknown_is_not_none():
    from normalization import UNKNOWN
    assert _is_no_assignee(_t(assignee=None)) is True
    assert _is_no_assignee(_t(assignee=UNKNOWN)) is False  # UNKNOWN != «нет»