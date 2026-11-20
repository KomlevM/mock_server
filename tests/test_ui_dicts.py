# -*- coding: utf-8 -*-
"""UI-справочники: стабильные id, подписи, спец-элементы. DECISIONS 3.5."""
import pytest

from normalization import (
    statuses_for_ui, priorities_for_ui, projects_for_ui, users_for_ui,
    tags_for_ui, sort_for_ui, UNKNOWN_ID, FILTER_NONE_ID,
)


def _ids(items):
    return [i["id"] for i in items]


def test_statuses_for_ui_stable_ids():
    items = statuses_for_ui()
    assert _ids(items)[:6] == [1, 2, 3, 4, 5, 6]
    assert UNKNOWN_ID in _ids(items)
    assert FILTER_NONE_ID in _ids(items)
    for i in items:
        assert isinstance(i["id"], int)
        assert "label" in i


def test_priorities_for_ui_stable_ids():
    items = priorities_for_ui()
    assert _ids(items)[:4] == [1, 2, 3, 4]
    assert UNKNOWN_ID in _ids(items)
    assert FILTER_NONE_ID in _ids(items)


def test_projects_for_ui_real(projects_raw):
    items = projects_for_ui(projects_raw)
    ids = _ids(items)
    assert 1 in ids and 6 in ids
    labels = {i["label"] for i in items}
    assert "Биллинг" in labels
    assert "landing-q4" in labels
    assert UNKNOWN_ID in ids
    assert FILTER_NONE_ID in ids


def test_users_for_ui_only_active(users_raw):
    items = users_for_ui(users_raw, only_active=True)
    labels = {i["label"] for i in items}
    assert "И. Петров" in labels
    assert "Иван (старый)" not in labels     # active: false скрыт


def test_users_for_ui_includes_inactive(users_raw):
    items = users_for_ui(users_raw, only_active=False)
    labels = {i["label"] for i in items}
    assert "Иван (старый)" in labels


def test_tags_for_ui():
    tasks = [{"tags": ["b", "a"]}, {"tags": ["a", "c"]}]
    items = tags_for_ui(tasks)
    labels = [i["label"] for i in items if i["id"] != FILTER_NONE_ID]
    assert labels == ["a", "b", "c"]


def test_sort_for_ui():
    s = sort_for_ui()
    assert {f["id"] for f in s["fields"]} == {"created", "due", "estimate"}
    assert {d["id"] for d in s["directions"]} == {"asc", "desc"}