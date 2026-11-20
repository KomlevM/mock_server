# -*- coding: utf-8 -*-
"""Исполнители/проекты: реальные users.json/projects.json, алиасы, коллизии."""
import pytest

from normalization import (
    _lookup_user_strict, _lookup_project_strict, _build_index,
    UNKNOWN,
)


@pytest.mark.parametrize("raw,canon", [
    ("petrov@corp.local", "И. Петров"),          # email
    ("s.volkova@corp.local", "С. Волкова"),
    ("mkozlov", "М. Козлов"),                    # login без домена
    ("@yulya_k", "Юля К."),                      # login с @
    ("И. Петров", "И. Петров"),                  # name
    ("Паша с мобилки", "Паша с мобилки"),        # name, задача 44
    ("тот кто на поддержке", "тот кто на поддержке"),  # name, login: null
    ("ivan.old", "Иван (старый)"),
    (11, "И. Петров"),                           # id
    ("11", "И. Петров"),
])
def test_lookup_user_real(users_index, raw, canon):
    assert _lookup_user_strict(users_index, raw) == canon


@pytest.mark.parametrize("raw", [None, "", "—", "не назначено", "TODO", "unassigned"])
def test_lookup_user_empty_markers(users_index, raw):
    assert _lookup_user_strict(users_index, raw) is None


def test_lookup_user_unknown(users_index):
    assert _lookup_user_strict(users_index, "Вася Пупкин") == UNKNOWN


@pytest.mark.parametrize("raw,canon", [
    ("Внутрянка", "Внутрянка"),
    ("admin", "Внутрянка"),                      # PROJECT_ALIASES internal
    ("internal-tools", "Внутрянка"),
    ("lp", "landing-q4"),                        # PROJECT_ALIASES landing
    ("billing-migration", "Биллинг"),            # PROJECT_ALIASES billing
    ("биллинг-миграция", "Биллинг"),
    ("ios+android", "Мобилка"),                  # PROJECT_ALIASES mobile
    (1, "Биллинг"), (5, "Внутрянка"),            # id
])
def test_lookup_project_real(projects_index, raw, canon):
    assert _lookup_project_strict(projects_index, raw) == canon


def test_lookup_project_unknown(projects_index):
    assert _lookup_project_strict(projects_index, "несуществующий") == UNKNOWN


def test_build_index_collision_yields_unknown():
    """Синтетика: на реальных данных коллизий нет."""
    raw = {"users": [
        {"id": 1, "name": "A", "login": "shared"},
        {"id": 2, "name": "B", "login": "shared"},
    ]}
    from normalization import _user_alias_keys, _user_canon
    idx = _build_index(raw, _user_alias_keys, _user_canon)
    assert idx["shared"] == UNKNOWN