# -*- coding: utf-8 -*-
"""apply_sort / normalize_sort. DECISIONS 3.7."""
import pytest

from normalization import apply_sort, normalize_sort


def _t(created=None, due=None, estimate=None):
    return {"created": created, "due": due, "estimate": estimate,
            "all_data": {"created": created, "due": due}}


def test_sort_created_asc():
    tasks = [_t(created="03.10.2026 18:17"), _t(created="01.01.2026 00:00")]
    out = apply_sort(tasks, "created", "asc")
    assert out[0]["created"] == "01.01.2026 00:00"


def test_sort_created_desc():
    tasks = [_t(created="01.01.2026 00:00"), _t(created="03.10.2026 18:17")]
    out = apply_sort(tasks, "created", "desc")
    assert out[0]["created"] == "03.10.2026 18:17"


def test_sort_none_last():
    tasks = [_t(created=None), _t(created="01.01.2026 00:00")]
    out = apply_sort(tasks, "created", "asc")
    assert out[-1]["created"] is None


@pytest.mark.parametrize("field", ["created", "due", "estimate"])
def test_sort_only_allowed_fields(field):
    tasks = [_t(created="01.01.2026 00:00")]
    assert apply_sort(tasks, field) == tasks


def test_sort_unknown_field_returns_as_is():
    tasks = [_t(created="01.01.2026 00:00")]
    assert apply_sort(tasks, "title") == tasks


def test_sort_negative_one_not_used():
    """DECISIONS 3.7: спец-id -1 в сортировке не используется."""
    field, direction = normalize_sort("-1", "asc")
    assert field is None
    assert direction == "asc"


@pytest.mark.parametrize("f,d,expected", [
    ("created", "asc", ("created", "asc")),
    ("due", "DESC", ("due", "desc")),
    ("created", "garbage", ("created", "asc")),
    ("title", "asc", (None, "asc")),
])
def test_normalize_sort(f, d, expected):
    assert normalize_sort(f, d) == expected