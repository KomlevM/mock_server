# -*- coding: utf-8 -*-
"""Интеграционный DTO по реальному all_data задачи 44."""
import pytest


def test_task_44_dto(task_44_dto):
    dto = task_44_dto
    assert dto["id"] == 44
    assert dto["key"] == "TB-44"
    assert dto["status"] == "NEW"           # all_data.status = "open"
    assert dto["status_id"] == 1
    assert dto["status_label"] == "Новый"
    assert dto["priority"] == "P2"          # all_data.priority = "normal"
    assert dto["priority_id"] == 3
    assert dto["priority_label"] == "Средний"
    assert dto["project"] == "Внутрянка"
    assert dto["project_id"] == 5
    assert dto["assignee"] == "Паша с мобилки"
    assert dto["assignee_id"] == 18
    assert dto["assignee_active"] is True
    assert dto["archived"] is False
    # DECISIONS 4: due=null, но due_ts=1791861420 -> 13.10.2026 03:17
    assert dto["created"] == "03.10.2026 18:17"
    assert dto["due"] == "13.10.2026 03:17"
    assert dto["updated"] is None
    assert dto["completed"] is None
    assert dto["estimate"] is None          # "" -> None
    assert dto["estimate_raw"] == ""
    assert dto["is_due_date_error"] is False
    assert dto["all_data"]["uuid"] == "04a1ad8424e3cd13935e296aafda975c"


def test_task_44_empty_comments(task_44_dto):
    # comments_by_task={} -> пустой список
    assert task_44_dto["comments"] == []


def test_task_41_fields(task_41_raw, users_index, projects_index, users_meta):
    from normalization import normalize_task
    dto = normalize_task(task_41_raw, users_index, projects_index, {}, users_meta)
    assert dto["status"] == "IN_PROGRESS"    # "in_progress"
    assert dto["priority"] == "P2"           # "2"
    assert dto["project"] == "Внутрянка"     # "admin" -> alias
    assert dto["estimate"] == 2.0            # "2h"
    assert dto["created"] == "18.09.2025 12:04"
    assert dto["due"] == "19.09.2025 12:24"  # due_ts=1758308640
    assert dto["assignee"] == "тот кто на поддержке"


def test_task_43_canceled_done(task_43_raw, users_index, projects_index, users_meta):
    """DECISIONS 12: canceled -> DONE — TBD."""
    from normalization import normalize_task
    dto = normalize_task(task_43_raw, users_index, projects_index, {}, users_meta)
    assert dto["status"] == "DONE"           # xfail при вынесении CANCELLED
    assert dto["priority"] == "P0"           # "p0"
    assert dto["project"] == "landing-q4"    # "lp"
    assert dto["estimate"] == 2.0            # число 2
    assert dto["assignee"] == "Д. Орлов"


def test_missing_fields_do_not_crash(users_index, projects_index, users_meta):
    """Пустой raw -> DTO с None/UNKNOWN, без исключений."""
    from normalization import normalize_task, UNKNOWN
    dto = normalize_task({}, users_index, projects_index, {}, users_meta)
    assert dto["title"] is None
    assert dto["status"] is None
    assert dto["priority"] is None
    assert dto["project"] is None
    assert dto["assignee"] is None
    assert dto["created"] is None
    assert dto["due"] is None
    assert dto["estimate"] is None
    assert dto["all_data"] == {}


def test_non_dict_raw(users_index, projects_index, users_meta):
    from normalization import normalize_task
    dto = normalize_task("garbage", users_index, projects_index, {}, users_meta)
    assert dto["all_data"] == {}