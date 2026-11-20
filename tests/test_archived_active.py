# -*- coding: utf-8 -*-
"""archived, assignee_active. DECISIONS 3.4, 5.1."""
import pytest

from normalization import _normalize_archived, _assignee_active, UNKNOWN


@pytest.mark.parametrize("raw,expected", [
    (None, False), (True, True), (False, False),
    (1, True), (0, False),
    ("1", True), ("true", True), ("yes", True), ("y", True),
    ("0", False), ("false", False), ("", False), ("garbage", False),
])
def test_normalize_archived(raw, expected):
    assert _normalize_archived({"archived": raw}) == expected


def test_normalize_archived_is_archived_alias():
    assert _normalize_archived({"is_archived": True}) is True


def test_assignee_active_real(users_meta):
    assert _assignee_active("И. Петров", users_meta) is True
    assert _assignee_active("Иван (старый)", users_meta) is False


def test_assignee_active_none_or_unknown(users_meta):
    assert _assignee_active(None, users_meta) is None
    assert _assignee_active(UNKNOWN, users_meta) is None


def test_assignee_active_no_meta_defaults_true(users_meta):
    assert _assignee_active("Кто-то неизвестный", users_meta) is True