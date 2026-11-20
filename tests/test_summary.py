# -*- coding: utf-8 -*-
"""compute_summary. DECISIONS 5.1."""
from normalization import compute_summary, UNKNOWN


def _t(status="NEW", assignee=None, priority=None, due=None, created=None,
       assignee_active=None):
    all_data = {}
    if due is not None:
        all_data["due"] = due
    if created is not None:
        all_data["created"] = created
    return {"status": status, "assignee": assignee, "priority": priority,
            "due": due, "created": created, "all_data": all_data,
            "assignee_active": assignee_active}


def test_summary_counts(now):
    tasks = [
        _t(status="IN_PROGRESS", due="2026-11-01T00:00:00Z", created="2026-10-01T00:00:00Z"),
        _t(status="DONE",        due="2026-11-01T00:00:00Z", created="2026-10-01T00:00:00Z"),
        _t(status="BLOCKED",     assignee="И. Петров", priority="P1"),
        _t(status="NEW",         due="2026-11-22T00:00:00Z", priority="P2",
           assignee="И. Петров", assignee_active=True),
        _t(status="NEW",         due="2026-12-30T00:00:00Z"),
        _t(status=None),
    ]
    s = compute_summary(tasks, 7, now=now)
    assert s["total"] == 6
    assert s["overdue"] == 1                 # DONE исключён
    assert s["no_assignee"] == 4             # None, но не UNKNOWN
    assert s["no_due"] == 2                  # у BLOCKED и status=None due=None
    assert s["no_priority"] == 2
    assert s["due_soon"] == 1                # 22.11 в пределах 7 дней
    assert s["is_due_date_error"] == 0
    assert s["no_active_assignee"] == 4
    assert s["due_within_days"] == 7
    assert s["by_status"]["__no_status__"] == 1


def test_summary_unknown_is_not_no_assignee(now):
    tasks = [_t(assignee=UNKNOWN, priority=UNKNOWN, status=UNKNOWN)]
    s = compute_summary(tasks, 7, now=now)
    assert s["no_assignee"] == 0             # UNKNOWN != None
    assert s["no_priority"] == 0
    assert s["unknown_data"] == 1


def test_summary_date_error(now):
    tasks = [_t(status="NEW", due="2026-01-01T00:00:00Z", created="2026-02-01T00:00:00Z")]
    s = compute_summary(tasks, 7, now=now)
    assert s["is_due_date_error"] == 1


def test_summary_due_within_days_invalid(now):
    tasks = [_t(due="2026-11-22T00:00:00Z")]
    s = compute_summary(tasks, "garbage", now=now)
    assert s["due_within_days"] == 7         # default


def test_summary_negative_n_reset(now):
    tasks = [_t(due="2026-11-22T00:00:00Z")]
    s = compute_summary(tasks, -5, now=now)
    assert s["due_within_days"] == 7