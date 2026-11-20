# -*- coding: utf-8 -*-
"""DECISIONS 3.1: mojibake чинится, валидная кириллица не трогается."""
import pytest

from normalization import _fix_mojibake


@pytest.mark.parametrize("broken,fixed", [
    ("ÐŸÑ€Ð¸Ð²ÐµÑ‚", "Привет"),                      # UTF-8 как Latin-1
    ("Â«Ñ‚ÐµÑ�Ñ‚Â»", "«тест»"),
    ("Ð—Ð°Ð´Ð°Ñ‡Ð° â€” Ñ‚ÐµÑ�Ñ‚", "Задача — тест"),  # CP1252 (—, €)
])
def test_fix_mojibake(broken, fixed):
    assert _fix_mojibake(broken) == fixed


@pytest.mark.parametrize("valid", ["Привет", "Задача — тест", "«ёлка»", "", "abc"])
def test_valid_cyrillic_untouched(valid):
    """Страж: не портим валидный текст."""
    assert _fix_mojibake(valid) == valid


@pytest.mark.parametrize("raw", [None, 123, True, [], {}])
def test_non_string_passthrough(raw):
    assert _fix_mojibake(raw) == raw