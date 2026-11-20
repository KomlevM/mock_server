# -*- coding: utf-8 -*-
"""Фикстуры: реальные users/projects/задачи из дампов + детерминированный now."""
import json
import os
from datetime import datetime, timezone

import pytest

from normalization import (
    build_users_index, build_users_meta, build_projects_index, normalize_task,
)

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def users_raw():
    return _load("users.json")


@pytest.fixture(scope="session")
def projects_raw():
    return _load("projects.json")


@pytest.fixture(scope="session")
def users_index(users_raw):
    return build_users_index(users_raw)


@pytest.fixture(scope="session")
def users_meta(users_raw):
    return build_users_meta(users_raw)


@pytest.fixture(scope="session")
def projects_index(projects_raw):
    return build_projects_index(projects_raw)


@pytest.fixture(scope="session")
def task_44_raw():
    return _load("task_44_all_data.json")


@pytest.fixture(scope="session")
def task_41_raw():
    return _load("task_41_raw.json")


@pytest.fixture(scope="session")
def task_43_raw():
    return _load("task_43_raw.json")


@pytest.fixture(scope="session")
def task_44_dto(task_44_raw, users_index, projects_index, users_meta):
    # Без comments_by_task: комментарии в all_data, но normalize_task читает
    # comments_by_task; для DTO-теста передаём пустой dict и проверяем comments отдельно.
    return normalize_task(task_44_raw, users_index, projects_index, {}, users_meta)


@pytest.fixture
def now():
    # Фиксированный момент: 2026-11-20 12:00 UTC (дата сдачи).
    return datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)