# -*- coding: utf-8 -*-
"""
Нормализация «грязных» данных TaskBoard в TaskDto.

Политика:
  - пусто (None, "", " ", маркеры "не назначено"/"—"/"TODO" для assignee) -> None
  - есть и распознано                                                     -> канон
  - есть, но не распознано                                                -> UNKNOWN ("Неизвестно")
  - дата/estimate не парсится (но было непустым)                          -> UNKNOWN
  - сырьё всегда сохраняется в all_data

Каноны (внутреннее представление TaskDto):
  assignee -> name из users.json (например, "И. Петров")
  project  -> title из projects.json (например, "Внутрянка")
  status   -> "NEW" / "IN_PROGRESS" / ... / "Неизвестно"
  priority -> "P0" / "P1" / "P2" / "P3" / "Неизвестно"

Числовые id (для API/UI):
  Все id, отдаваемые фронту, — целые числа.
    UNKNOWN_ID = 0       — «Неизвестно» (было значение, но не распознали)
    FILTER_NONE_ID = -1  — «Нет значения» (значения не было)
  status/priority/tag — стабильные int из диапазона 1..100 (без хэшей),
    задаются явными таблицами _STATUS_IDS / _PRIORITY_IDS / TAG_IDS.
  project/assignee — реальные id из справочников (приводятся к int).

Русские подписи:
  Для фронта в TaskDto дополнительно отдаются:
    status_id, status_label       (например, 1, "Новый")
    priority_id, priority_label   (например, 10, "Крит")
  В UI-справочниках /filters — те же id + русские label.

Mojibake:
  Текст, прочитанный не в той кодировке (UTF-8 как Latin-1 или CP1252),
  чинится одним проходом _fix_mojibake. Если в строке есть символ вне
  Latin-1/CP1252 (например, настоящая кириллица) — строка возвращается
  без изменений (это не mojibake).

Даты:
  В TaskDto — dd.mm.yyyy HH:MM (или "Неизвестно"/null).
  Для вычислений (overdue, due_soon, is_due_date_error) даты парсятся
  из all_data (ISO/Unix-ms), секунды сохраняются.

Комментарии:
  normalize_task принимает comments_by_task (dict: task_id/task_key -> [raw]).
  В DTO: comments: [{author, created, text}], новые сверху.

Вычисляемые поля TaskDto:
  archived            — boolean: true/false.
  is_due_date_error   — boolean: true только если обе даты есть и due < created.
  assignee_active     — boolean|null.

Фильтры в /tasks:
  assignee_active: false — только явно неактивные (active: false в users.json).
  assignee_active: true  — активные + без исполнителя + "Неизвестно".

  «Нет значения» в фильтрах: status/priority/project/assignee/tag принимают
  FILTER_NONE_ID (-1), который матчит отсутствующее значение (None для
  скалярных полей, пустой список для tags). UNKNOWN (0) — значение было,
  но не распознали; это разные вещи.

  Приём фильтров: status/priority/tag принимают как int-id, так и строку-канон
  (для обратной совместимости и удобства ручных curl-запросов).

Сортировка:
  Только по created / due / estimate. Спец-id -1 в сортировке не используется.

Summary:
  compute_summary(tasks, due_within_days, now) — счётчики:
    total, overdue, no_assignee, unknown_data, no_due, no_priority,
    date_error, due_soon, due_within_days, by_status, no_active_assignee.
"""

import re
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

UNKNOWN = "Неизвестно"

UNKNOWN_ID = 0
FILTER_NONE_ID = -1

MAX_FILTER_LIST = 50
HOURS_PER_DAY = 8.0
DUE_SOON_DEFAULT_DAYS = 7

# --- Каноны статусов + русские подписи + числовые id (1..100) --------------

STATUS_LABELS = {
    "NEW":         "Новый",
    "IN_PROGRESS": "В работе",
    "CODE_REVIEW": "На ревью",
    "BLOCKED":     "Заблокирован",
    "HOLD":        "На паузе",
    "DONE":        "Готово",
}

# Явные стабильные id (1..100). Не менять без миграции фронта.
STATUS_IDS = {
    "NEW":         1,
    "IN_PROGRESS": 2,
    "CODE_REVIEW": 3,
    "BLOCKED":     4,
    "HOLD":        5,
    "DONE":        6,
}

STATUS_ALIASES = {
    "NEW":         {"new", "open", "tod", "todo", "ждут"},
    "IN_PROGRESS": {"in_proges", "in-proges", "inproges", "inprogress",
                    "in_progress", "in-progress", "doing", "в работе"},
    "CODE_REVIEW": {"reviw", "code_rviw", "review", "code_review", "на ревью"},
    "BLOCKED":     {"blocked"},
    "HOLD":        {"hold"},
    "DONE":        {"done", "resolvd", "resolved", "готв", "готово",
                    "closed", "caneld", "canceled", "cancelled"},
}

# --- Каноны приоритетов + русские подписи + числовые id (1..100) -----------

PRIORITY_LABELS = {
    "P0": "Крит",
    "P1": "Высокий",
    "P2": "Средний",
    "P3": "Низкий",
}

# Явные стабильные id (1..100). Не пересекаются со STATUS_IDS намеренно
# (разные пространства; фронт различает по полю справочника).
PRIORITY_IDS = {
    "P0": 1,
    "P1": 2,
    "P2": 3,
    "P3": 4,
}

PRIORITY_ALIASES = {
    "P0": {"0", "p0", "крит", "critical", "blocker"},
    "P1": {"1", "p1", "high", "urgent", "высокий"},
    "P2": {"2", "p2", "normal", "medium", "средний"},
    "P3": {"3", "p3", "low", "низкий"},
}

# --- Проекты ---------------------------------------------------------------

PROJECT_ALIASES = {
    "billing":  {"billing-migration", "биллинг-миграция"},
    "site":     {"website-refresh"},
    "mobile":   {"ios+android", "mobile-app-v2"},
    "docs":     {"docs-portal"},
    "internal": {"internal-tools", "admin"},
    "landing":  {"lp", "новый лендинг"},
}

# --- Фильтры ---------------------------------------------------------------

FILTER_FIELDS = {
    "status":            "eq",
    "priority":          "eq",
    "project":           "eq",
    "assignee":          "eq",
    "tag":               "in_tags",
    "archived":          "bool",
    "due_within_days":   "due_within",
    "overdue":           "computed_bool",
    "no_assignee":       "computed_bool",
    "unknown_data":      "computed_bool",
    "no_due":            "computed_bool",
    "no_priority":       "computed_bool",
    "is_due_date_error": "computed_bool",
    "assignee_active":   "computed_bool",
}

SORT_KEYS = {
    "created":  lambda t: parse_dt(t.get("created")),
    "due":      lambda t: parse_dt(t.get("due")),
    "estimate": lambda t: (t.get("estimate") if isinstance(t.get("estimate"), (int, float)) else None),
}

_EMPTY_ASSIGNEE = {
    "", "—", "-", "–", "null", "none", "n/a", "na",
    "не назначено", "не назначен", "нет", "todo",
    "без исполнителя", "unassigned",
}

_STOP_TOKENS = {"corp", "local", "com", "ru", "net", "org", "mail", "email"}
_MIN_TOKEN_LEN = 3

_DOMAIN_RE = re.compile(r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_TOKEN_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)

# ---------------------------------------------------------------------------
# Числовые id: общие хелперы
# ---------------------------------------------------------------------------

def _to_int_id(value, fallback=None):
    """Приводит id справочника к int.

    Числа и числовые строки -> int. Нечисловые строки -> stable int из 1..100
    через crc32 (только для нестандартных id, которых нет в явных таблицах;
    для штатных статусов/приоритетов используются STATUS_IDS/PRIORITY_IDS).
    """
    if value is None:
        return fallback
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip()
    if not s:
        return fallback
    try:
        return int(s)
    except ValueError:
        # Стабильный int 1..100 для нестандартных строковых id.
        import zlib
        h = zlib.crc32(s.encode("utf-8")) % 100 + 1
        return h


# ---------------------------------------------------------------------------
# Mojibake
# ---------------------------------------------------------------------------

_CP1252_TO_BYTE = {
    "\u20ac": 0x80, "\u201a": 0x82, "\u0192": 0x83, "\u201e": 0x84,
    "\u2026": 0x85, "\u2020": 0x86, "\u2021": 0x87, "\u02c6": 0x88,
    "\u2030": 0x89, "\u0160": 0x8a, "\u2039": 0x8b, "\u0152": 0x8c,
    "\u017d": 0x8e, "\u2018": 0x91, "\u2019": 0x92, "\u201c": 0x93,
    "\u201d": 0x94, "\u2022": 0x95, "\u2013": 0x96, "\u2014": 0x97,
    "\u02dc": 0x98, "\u2122": 0x99, "\u0161": 0x9a, "\u203a": 0x9b,
    "\u0153": 0x9c, "\u017e": 0x9e, "\u0178": 0x9f,
}


def _fix_mojibake(s):
    if not isinstance(s, str) or not s:
        return s
    buf = bytearray()
    for ch in s:
        b = _CP1252_TO_BYTE.get(ch)
        if b is not None:
            buf.append(b)
            continue
        try:
            buf += ch.encode("latin-1")
        except UnicodeEncodeError:
            return s
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return s


# ---------------------------------------------------------------------------
# Алиасы статусов/приоритетов
# ---------------------------------------------------------------------------

def _build_alias_index(aliases):
    idx = {}
    for canon, raws in aliases.items():
        idx[canon.strip().lower()] = canon
        for r in raws:
            idx[str(r).strip().lower()] = canon
    return idx


_STATUS_INDEX = _build_alias_index(STATUS_ALIASES)
_PRIORITY_INDEX = _build_alias_index(PRIORITY_ALIASES)

# Обратные индексы int-id -> канон (для приёма фильтров по числовому id).
_STATUS_ID_TO_CANON = {v: k for k, v in STATUS_IDS.items()}
_PRIORITY_ID_TO_CANON = {v: k for k, v in PRIORITY_IDS.items()}


def normalize_status(raw):
    if raw is None:
        return None
    s = _fix_mojibake(str(raw).strip())
    if not s:
        return None
    return _STATUS_INDEX.get(s.lower(), UNKNOWN)


def normalize_priority(raw):
    if raw is None:
        return None
    s = _fix_mojibake(str(raw).strip())
    if not s:
        return None
    if not _PRIORITY_INDEX:
        return UNKNOWN
    return _PRIORITY_INDEX.get(s.lower(), UNKNOWN)


def status_id(canon):
    """Канон статуса -> int-id. UNKNOWN/None -> UNKNOWN_ID."""
    if canon is None or canon == UNKNOWN:
        return UNKNOWN_ID
    return STATUS_IDS.get(canon, UNKNOWN_ID)


def priority_id(canon):
    if canon is None or canon == UNKNOWN:
        return UNKNOWN_ID
    return PRIORITY_IDS.get(canon, UNKNOWN_ID)


def status_label(canon):
    """Канон статуса -> русская подпись (или "Неизвестно"/None)."""
    if canon is None:
        return None
    if canon == UNKNOWN:
        return UNKNOWN
    return STATUS_LABELS.get(canon, canon)


def priority_label(canon):
    if canon is None:
        return None
    if canon == UNKNOWN:
        return UNKNOWN
    return PRIORITY_LABELS.get(canon, canon)


def _status_from_filter(v):
    """Принимает int-id, строку-канон/алиас, -1/0. Возвращает канон или спец-id."""
    if _is_none_id(v):
        return FILTER_NONE_ID
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = int(v)
        if n == UNKNOWN_ID:
            return UNKNOWN
        return _STATUS_ID_TO_CANON.get(n)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            n = int(s)
            if n == UNKNOWN_ID:
                return UNKNOWN
            if n == FILTER_NONE_ID:
                return FILTER_NONE_ID
            return _STATUS_ID_TO_CANON.get(n)
        return normalize_status(s)
    return None


def _priority_from_filter(v):
    if _is_none_id(v):
        return FILTER_NONE_ID
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = int(v)
        if n == UNKNOWN_ID:
            return UNKNOWN
        return _PRIORITY_ID_TO_CANON.get(n)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            n = int(s)
            if n == UNKNOWN_ID:
                return UNKNOWN
            if n == FILTER_NONE_ID:
                return FILTER_NONE_ID
            return _PRIORITY_ID_TO_CANON.get(n)
        return normalize_priority(s)
    return None


# ---------------------------------------------------------------------------
# Токены / домены
# ---------------------------------------------------------------------------

def _tokens(s):
    return {t for t in _TOKEN_SPLIT_RE.split(str(s).lower()) if len(t) >= _MIN_TOKEN_LEN}


def _strip_domain(s):
    return _DOMAIN_RE.sub("", str(s).strip()).lstrip("@")


# ---------------------------------------------------------------------------
# Estimate -> часы
# ---------------------------------------------------------------------------

_EST_RE = re.compile(
    r"^\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Zа-яА-Я]*)?\s*$",
    re.IGNORECASE,
)

_UNIT_TO_HOURS = {
    "": 1.0,
    "h": 1.0, "ч": 1.0, "час": 1.0, "часа": 1.0, "часов": 1.0,
    "d": HOURS_PER_DAY, "д": HOURS_PER_DAY,
    "день": HOURS_PER_DAY, "дня": HOURS_PER_DAY, "дней": HOURS_PER_DAY,
}


def normalize_estimate(raw):
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s or s == "?":
        return None
    m = _EST_RE.match(s)
    if not m:
        return None
    num = float(m.group("num").replace(",", "."))
    unit = (m.group("unit") or "").lower()
    factor = _UNIT_TO_HOURS.get(unit)
    return num * factor if factor is not None else None


# ---------------------------------------------------------------------------
# Даты
# ---------------------------------------------------------------------------

_DT_OUT_FMT = "%d.%m.%Y %H:%M"
_DT_IN_FMTS = ("%d.%m.%Y %H:%M", "%d.%m.%Y")


def parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v > 1e12:
            v /= 1000.0
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        for fmt in _DT_IN_FMTS:
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def normalize_dt(value):
    dt = parse_dt(value)
    return dt.strftime(_DT_OUT_FMT) if dt else None


def _normalize_dt_or_unknown(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    dt = parse_dt(value)
    if dt is None:
        return UNKNOWN
    return dt.strftime(_DT_OUT_FMT)


def _normalize_estimate_or_unknown(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if value == "?":
        return None
    est = normalize_estimate(value)
    return est if est is not None else UNKNOWN


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

def _iter_records(raw):
    if raw is None:
        return []
    if isinstance(raw, dict):
        for k in ("users", "projects", "data", "items"):
            if isinstance(raw.get(k), list):
                return raw[k]
        return []
    if isinstance(raw, list):
        return raw
    return []


def _user_alias_keys(rec):
    keys = set()
    if rec.get("id") is not None:
        keys.add(str(rec["id"]).strip().lower())
    for f in ("login", "username", "email"):
        v = rec.get(f)
        if v is None or str(v) == "":
            continue
        raw = str(v).strip()
        keys.add(raw.lower())
        local = _strip_domain(raw).lower()
        if local:
            keys.add(local)
            keys |= _tokens(local)
    for f in ("name", "display_name"):
        v = rec.get(f)
        if v is None or str(v) == "":
            continue
        keys.add(str(v).strip().lower())
        keys |= _tokens(v)
    keys -= _STOP_TOKENS
    return {k for k in keys if k}


def _user_canon(rec):
    for f in ("name", "display_name", "login", "username", "email", "id"):
        v = rec.get(f)
        if v is not None and str(v) != "":
            return str(v)
    return None


def _build_index(raw, alias_fn, canon_fn):
    idx = {}
    collisions = {}
    for rec in _iter_records(raw):
        if not isinstance(rec, dict):
            continue
        canon = canon_fn(rec)
        if canon is None:
            continue
        for k in alias_fn(rec):
            if k in idx and idx[k] != canon:
                collisions.setdefault(k, {idx[k], canon})
            else:
                idx[k] = canon
    for k, canons in collisions.items():
        if len(canons) > 1:
            idx[k] = UNKNOWN
    return idx


def build_users_index(raw):
    return _build_index(raw, _user_alias_keys, _user_canon)


def build_users_meta(raw):
    """canon -> {"active": True|False|None, "id": int}. None — поле active отсутствует."""
    meta = {}
    for rec in _iter_records(raw):
        if not isinstance(rec, dict):
            continue
        canon = _user_canon(rec)
        if canon is None:
            continue
        active = rec.get("active")
        meta[canon] = {
            "active": active if isinstance(active, bool) else None,
            "id": _to_int_id(rec.get("id"), fallback=None),
        }
    return meta


def _project_alias_keys(rec, slug):
    keys = set()
    if rec.get("id") is not None:
        keys.add(str(rec["id"]).strip().lower())
    for f in ("slug", "key", "name", "title"):
        v = rec.get(f)
        if v is not None and str(v) != "":
            keys.add(str(v).strip().lower())
    if slug and slug in PROJECT_ALIASES:
        for a in PROJECT_ALIASES[slug]:
            keys.add(str(a).strip().lower())
    return keys


def _project_canon(rec):
    for f in ("title", "name", "slug", "key", "id"):
        v = rec.get(f)
        if v is not None and str(v) != "":
            return str(v)
    return None


def _project_keys_for(rec):
    slug = str(rec.get("slug") or "").strip().lower()
    return _project_alias_keys(rec, slug)


def build_projects_index(raw):
    return _build_index(raw, _project_keys_for, _project_canon)


def _lookup_user_strict(index, value):
    if value is None:
        return None
    s = _fix_mojibake(str(value).strip())
    if not s or s.lower() in _EMPTY_ASSIGNEE:
        return None
    if not index:
        return UNKNOWN
    s_low = s.lower()
    if s_low in index:
        return index[s_low]
    bare = _strip_domain(s).lower()
    if bare and bare in index:
        return index[bare]
    toks = _tokens(s) - _STOP_TOKENS
    if toks:
        matches = {index[t] for t in toks if t in index}
        if len(matches) == 1:
            return next(iter(matches))
        if len(matches) > 1:
            return UNKNOWN
    return UNKNOWN


def _lookup_project_strict(index, value):
    if value is None:
        return None
    s = _fix_mojibake(str(value).strip())
    if not s:
        return None
    if not index:
        return UNKNOWN
    canon = index.get(s.lower())
    return canon if canon is not None else UNKNOWN


# ---------------------------------------------------------------------------
# TaskDto
# ---------------------------------------------------------------------------

def _first(raw, *names):
    for n in names:
        v = raw.get(n)
        if v is not None and v != "":
            return v
    return None


def _normalize_tags(raw):
    tags = raw.get("tags")
    if isinstance(tags, list):
        return [_fix_mojibake(str(t)) for t in tags if t is not None and str(t) != ""]
    if isinstance(tags, str) and tags.strip():
        return [_fix_mojibake(t.strip()) for t in tags.split(",") if t.strip()]
    return []


def _normalize_archived(raw):
    v = _first(raw, "archived", "is_archived")
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return False


def _assignee_active(assignee, users_meta):
    """True/False/None по правилу (C)."""
    if assignee is None or assignee == UNKNOWN:
        return None
    if not users_meta:
        return True
    meta = users_meta.get(assignee)
    if not meta:
        return True
    active = meta.get("active")
    if active is None:
        return True
    return bool(active)


_UNKNOWN_FIELDS_FOR_SUMMARY = (
    "status", "priority", "project", "assignee",
    "created", "due", "updated", "completed", "estimate",
)


def _has_unknown_data(task):
    for f in _UNKNOWN_FIELDS_FOR_SUMMARY:
        if task.get(f) == UNKNOWN:
            return True
    return False


def _due_dt_from_raw(raw):
    return parse_dt(_first(raw, "due", "due_date", "due_utc", "due_ts", "due_local"))


def _created_dt_from_raw(raw):
    return parse_dt(_first(raw, "created", "created_at", "created_ts"))


def _is_overdue(task, now):
    due = _due_dt_from_raw(task.get("all_data") or {})
    if due is None:
        return False
    if task.get("status") == "DONE":
        return False
    return due < now


def _is_no_assignee(task):
    return task.get("assignee") is None


def _is_no_due(task):
    return task.get("due") is None


def _is_no_priority(task):
    return task.get("priority") is None


def _is_due_date_error(task):
    raw = task.get("all_data") or {}
    due = _due_dt_from_raw(raw)
    created = _created_dt_from_raw(raw)
    if due is None or created is None:
        return False
    return due < created


def _is_due_soon(task, now, n_days):
    due = _due_dt_from_raw(task.get("all_data") or {})
    if due is None:
        return False
    delta = (due - now).total_seconds()
    if delta < 0:
        return False
    return delta <= n_days * 86400


def _is_no_active_assignee(task):
    return task.get("assignee") is None or task.get("assignee_active") is False


def _is_assignee_active_only(task):
    """Для фильтра assignee_active: true — активные + null."""
    return task.get("assignee_active") is not False


_COMPUTED_BOOL = {
    "overdue":           lambda t, now, n: _is_overdue(t, now),
    "no_assignee":       lambda t, now, n: _is_no_assignee(t),
    "unknown_data":      lambda t, now, n: _has_unknown_data(t),
    "no_due":            lambda t, now, n: _is_no_due(t),
    "no_priority":       lambda t, now, n: _is_no_priority(t),
    "is_due_date_error": lambda t, now, n: _is_due_date_error(t),
    "assignee_active":   lambda t, now, n: _is_assignee_active_only(t),
}


def _normalize_comments(raw_comments, users_index, users_meta=None):
    if not raw_comments:
        return []
    out = []
    for c in raw_comments:
        if not isinstance(c, dict):
            continue
        text_raw = c.get("text")
        text = _fix_mojibake(text_raw) if isinstance(text_raw, str) else text_raw
        author = _lookup_user_strict(users_index, c.get("author"))
        author_id = UNKNOWN_ID
        if author and author != UNKNOWN and users_meta:
            meta = users_meta.get(author) or {}
            author_id = _to_int_id(meta.get("id"), fallback=UNKNOWN_ID)
        created_dt = parse_dt(c.get("created"))
        created = created_dt.strftime(_DT_OUT_FMT) if created_dt else None
        try:
            cid_num = int(c.get("id"))
        except (TypeError, ValueError):
            cid_num = -1
        out.append({
            "author": author,
            "author_id": author_id,
            "created": created,
            "text": text,
            "_sort_dt": created_dt,
            "_sort_id": cid_num,
        })
    _MIN = datetime.min.replace(tzinfo=timezone.utc)
    out.sort(key=lambda x: (
        x["_sort_dt"] is None,
        -(x["_sort_dt"] or _MIN).timestamp(),
        -x["_sort_id"],
    ))
    for c in out:
        c.pop("_sort_dt", None)
        c.pop("_sort_id", None)
    return out


def _comments_for_task(raw, comments_by_task):
    if not comments_by_task:
        return []
    task_id = raw.get("id")
    task_key = raw.get("key")
    if task_id is not None:
        got = comments_by_task.get(str(task_id))
        if got:
            return got
    if task_key is not None:
        got = comments_by_task.get(str(task_key))
        if got:
            return got
    return []


def normalize_task(raw, users_index=None, projects_index=None,
                   comments_by_task=None, users_meta=None, now = datetime.now(timezone.utc)):
    if not isinstance(raw, dict):
        raw = {}
    users_index = users_index or {}
    projects_index = projects_index or {}

    status = normalize_status(_first(raw, "status"))
    priority = normalize_priority(_first(raw, "priority"))
    assignee = _lookup_user_strict(
        users_index, _first(raw, "assignee", "assignee_id", "assignee_login"),
    )
    project = _lookup_project_strict(
        projects_index, _first(raw, "project", "project_id", "project_key"),
    )

    title_raw = raw.get("title")
    title = _fix_mojibake(title_raw) if isinstance(title_raw, str) else title_raw

    # Числовые id для фронта
    s_id = status_id(status)
    p_id = priority_id(priority)

    # Для отображения исходных грязных данных
    raw_comments = _comments_for_task(raw, comments_by_task)
    all_data = raw
    all_data["comments_raw"] = raw_comments

    # id проекта/исполнителя из справочников (для фронта)
    project_id_int = UNKNOWN_ID
    if project is not None:
        # project — канон (title). Найдём его id в projects_index по обратному
        # проходу нецелесообразно; проще взять из all_data и привести.
        project_id_int = _to_int_id(
            _first(raw, "project_id", "project") or project,
            fallback=UNKNOWN_ID,
        )

    assignee_id_int = UNKNOWN_ID
    if assignee is not None:
        if assignee == UNKNOWN:
            assignee_id_int = UNKNOWN_ID
        else:
            meta = (users_meta or {}).get(assignee) or {}
            assignee_id_int = _to_int_id(meta.get("id"), fallback=UNKNOWN_ID)

    tags = _normalize_tags(raw)
    tag_items = [{"id": _to_int_id(t), "label": t} for t in tags]

    task = {
        "id": raw.get("id"),
        "key": raw.get("key"),
        "source": raw.get("source"),
        "title": title,
        "description": raw.get("description"),
        # Каноны (внутреннее представление)
        "status": status,
        "priority": priority,
        "project": project,
        "assignee": assignee,
        # Готово для фронта: числовые id + русские подписи
        "status_id": s_id,
        "status_label": status_label(status),
        "priority_id": p_id,
        "priority_label": priority_label(priority),
        "project_id": project_id_int,
        "assignee_id": assignee_id_int,
        "tags": tags,
        "tags_items": tag_items,
        # Прочее
        "assignee_active": _assignee_active(assignee, users_meta),
        "archived": _normalize_archived(raw),
        "created":   _normalize_dt_or_unknown(_first(raw, "created", "created_at", "created_ts")),
        "due":       _normalize_dt_or_unknown(_first(raw, "due", "due_date", "due_utc", "due_ts", "due_local")),
        "updated":   _normalize_dt_or_unknown(_first(raw, "updated", "updated_at", "updated_ts")),
        "completed": _normalize_dt_or_unknown(_first(raw, "completed", "completed_at", "completed_ts")),
        "estimate": _normalize_estimate_or_unknown(raw.get("estimate")),
        "estimate_raw": raw.get("estimate"),
        "comments": _normalize_comments(
            _comments_for_task(raw, comments_by_task), users_index, users_meta,
        ),
        "all_data": all_data,
    }
    task["is_due_date_error"] = _is_due_date_error(task)
    task["is_overdue"] = _is_overdue(task, now)
    return task


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------

def _parse_int(value, default=None, lo=None, hi=None):
    if value is None or value == "":
        result = default
    else:
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = default
    if result is None:
        return None
    if lo is not None:
        result = max(lo, result)
    if hi is not None:
        result = min(hi, result)
    return result


def _as_list(value):
    return value if isinstance(value, (list, tuple)) else [value]


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return None


def _is_none_id(value):
    """True, если value — спец-id FILTER_NONE_ID (-1) в любом виде (int/str)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return int(value) == FILTER_NONE_ID
    if isinstance(value, str):
        return value.strip() == str(FILTER_NONE_ID)
    return False


def normalize_filters(raw_filters, users_index=None, projects_index=None):

    if not isinstance(raw_filters, dict):
        return {}
    users_index = users_index or {}
    projects_index = projects_index or {}
    out = {}

    for name, value in raw_filters.items():
        mode = FILTER_FIELDS.get(name)
        if mode is None or value is None:
            continue

        if mode in ("bool", "computed_bool"):
            b = _to_bool(value)
            if b is not None:
                out[name] = b
            continue

        if name == "due_within_days":
            n = _parse_int(value, default=None, lo=0)
            if n is not None:
                out[name] = n
            continue

        if name == "status":
            is_list = isinstance(value, (list, tuple))
            canon = []
            for v in _as_list(value):
                c = _status_from_filter(v)
                if c is not None:
                    canon.append(c)
            if canon:
                out[name] = canon if is_list else canon[0]
            continue

        if name == "priority":
            is_list = isinstance(value, (list, tuple))
            canon = []
            for v in _as_list(value):
                c = _priority_from_filter(v)
                if c is not None:
                    canon.append(c)
            if canon:
                out[name] = canon if is_list else canon[0]
            continue

        if name == "assignee":
            is_list = isinstance(value, (list, tuple))
            canon = []
            for v in _as_list(value):
                if _is_none_id(v):
                    canon.append(FILTER_NONE_ID)
                    continue
                if v is None or v == "":
                    continue
                r = _lookup_user_strict(users_index, v)
                if r is not None:
                    canon.append(r)
            if canon:
                out[name] = canon if is_list else canon[0]
            continue

        if name == "project":
            is_list = isinstance(value, (list, tuple))
            canon = []
            for v in _as_list(value):
                if _is_none_id(v):
                    canon.append(FILTER_NONE_ID)
                    continue
                if v is None or v == "":
                    continue
                r = _lookup_project_strict(projects_index, v)
                if r is not None:
                    canon.append(r)
            if canon:
                out[name] = canon if is_list else canon[0]
            continue

        if name == "tag":
            is_list = isinstance(value, (list, tuple))
            vals = []
            for v in _as_list(value):
                if _is_none_id(v):
                    vals.append(FILTER_NONE_ID)
                elif v is not None and v != "":
                    vals.append(v)
            if vals:
                out[name] = vals if is_list else vals[0]
            continue

        if isinstance(value, (list, tuple)):
            values = [v for v in value if v is not None and v != ""][:MAX_FILTER_LIST]
            if values:
                out[name] = values
        else:
            if value != "":
                out[name] = value
    return out


def _match_eq(actual, expected):
    if isinstance(expected, (list, tuple, set)):
        return any(_match_eq(actual, e) for e in expected)
    if _is_none_id(expected):
        return actual is None
    if actual is None:
        return False
    if actual == UNKNOWN:
        # Сравнение "Неизвестно" (строка в DTO) с 0 (int в фильтре)
        return _to_int_id(expected) == UNKNOWN_ID or str(expected) == UNKNOWN
    return _to_int_id(actual) == _to_int_id(expected)


def _match_in_tags(tags, expected):
    if isinstance(expected, (list, tuple, set)):
        return any(_match_in_tags(tags, e) for e in expected)
    if _is_none_id(expected):
        return not tags
    if not tags:
        return False
    if not isinstance(tags, (list, tuple, set)):
        tags = [tags]
    exp_id = _to_int_id(expected)
    return any(_to_int_id(t) == exp_id for t in tags)


def _match_bool(actual, expected):
    if isinstance(actual, str):
        actual = actual.strip().lower() in ("1", "true", "yes", "y")
    elif isinstance(actual, (int, float)) and not isinstance(actual, bool):
        actual = bool(actual)
    return bool(actual) is expected


def _raw_field(task, *names):
    all_data = task.get("all_data") or {}
    return _first(all_data, *names)


def apply_filters(tasks, filters, now=None):
    if not filters:
        return list(tasks), {}

    if now is None:
        now = datetime.now(timezone.utc)
    n_days = filters.get("due_within_days") or DUE_SOON_DEFAULT_DAYS
    applied = dict(filters)
    result = []

    for t in tasks:
        ok = True
        for name, expected in filters.items():
            mode = FILTER_FIELDS.get(name)

            if mode == "eq":
                if not _match_eq(t.get(name), expected):
                    ok = False
                    break

            elif mode == "in_tags":
                if not _match_in_tags(t.get("tags"), expected):
                    ok = False
                    break

            elif mode == "bool":
                actual = _raw_field(t, "archived", "is_archived")
                if not _match_bool(actual, expected):
                    ok = False
                    break

            elif mode == "computed_bool":
                fn = _COMPUTED_BOOL.get(name)
                if fn is None:
                    continue
                if fn(t, now, n_days) is not expected:
                    ok = False
                    break

            elif mode == "due_within":
                due = parse_dt(t.get("due"))
                if due is None:
                    ok = False
                    break
                try:
                    limit_dt = now + timedelta(days=expected)
                except OverflowError:
                    ok = False
                    break
                if due < now or due > limit_dt:
                    ok = False
                    break

        if ok:
            result.append(t)

    return result, applied


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def compute_summary(tasks, due_within_days, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        n = int(due_within_days)
    except (TypeError, ValueError):
        n = DUE_SOON_DEFAULT_DAYS
    if n < 0:
        n = DUE_SOON_DEFAULT_DAYS

    overdue = 0
    no_assignee = 0
    unknown_data = 0
    no_due = 0
    no_priority = 0
    is_due_date_error = 0
    due_soon = 0
    no_active_assignee = 0
    by_status = {}

    for t in tasks:
        if _is_overdue(t, now):
            overdue += 1
        if _is_no_assignee(t):
            no_assignee += 1
        if _has_unknown_data(t):
            unknown_data += 1
        if _is_no_due(t):
            no_due += 1
        if _is_no_priority(t):
            no_priority += 1
        if _is_due_date_error(t):
            is_due_date_error += 1
        if _is_due_soon(t, now, n):
            due_soon += 1
        if _is_no_active_assignee(t):
            no_active_assignee += 1

        key = t.get("status")
        if key is None:
            key = "__no_status__"
        by_status[key] = by_status.get(key, 0) + 1

    return {
        "total": len(tasks),
        "overdue": overdue,
        "no_assignee": no_assignee,
        "unknown_data": unknown_data,
        "no_due": no_due,
        "no_priority": no_priority,
        "is_due_date_error": is_due_date_error,
        "due_soon": due_soon,
        "no_active_assignee": no_active_assignee,
        "due_within_days": n,
        "by_status": by_status,
    }


# ---------------------------------------------------------------------------
# Сортировка (только created / due / estimate)
# ---------------------------------------------------------------------------

def apply_sort(tasks, field, direction="asc"):
    if field not in SORT_KEYS:
        return tasks
    reverse = direction == "desc"

    def _key(t):
        v = SORT_KEYS[field](t)
        if v is None:
            return (1, 0)
        if isinstance(v, datetime):
            ts = v.timestamp()
            return (0, -ts if reverse else ts)
        return (0, -v if reverse else v)

    return sorted(tasks, key=_key)


def normalize_sort(sort_field, sort_dir):
    direction = (sort_dir or "asc").lower()
    if direction not in ("asc", "desc"):
        direction = "asc"
    if sort_field not in SORT_KEYS:
        return None, direction
    return sort_field, direction


# ---------------------------------------------------------------------------
# UI-справочники (все id — int, подписи — русские)
# ---------------------------------------------------------------------------

def _is_known_status(value):
    return value is None or str(value).strip().lower() in _STATUS_INDEX


def _is_known_priority(value):
    if not _PRIORITY_INDEX:
        return True
    return value is None or str(value).strip().lower() in _PRIORITY_INDEX


def _unknown_item():
    return {"id": UNKNOWN_ID, "label": UNKNOWN, "special": True}


def _none_item(label):
    return {
        "id": FILTER_NONE_ID,
        "label": label,
        "special": True,
        "none_value": True,
    }


def unknown_values_for_ui(tasks, users_index=None, projects_index=None):
    users_index = users_index or {}
    projects_index = projects_index or {}
    unknown = {"status": set(), "priority": set(), "assignee": set(), "project": set()}

    for t in tasks:
        all_data = t.get("all_data") or {}

        s_raw = all_data.get("status")
        if s_raw is not None and str(s_raw).strip() and not _is_known_status(s_raw):
            unknown["status"].add(str(s_raw).strip())

        p_raw = all_data.get("priority")
        if p_raw is not None and str(p_raw).strip() and not _is_known_priority(p_raw):
            unknown["priority"].add(str(p_raw).strip())

        a_raw = all_data.get("assignee") or all_data.get("assignee_id") or all_data.get("assignee_login")
        if a_raw is not None and str(a_raw).strip():
            s = str(a_raw).strip()
            if s.lower() not in users_index and s.lower() not in _EMPTY_ASSIGNEE:
                unknown["assignee"].add(s)

        pr_raw = all_data.get("project") or all_data.get("project_id") or all_data.get("project_key")
        if pr_raw is not None and str(pr_raw).strip():
            s = str(pr_raw).strip()
            if s.lower() not in projects_index:
                unknown["project"].add(s)

    return {k: sorted(v) for k, v in unknown.items()}


def statuses_for_ui(unknown=None):
    out = [
        {"id": STATUS_IDS[c], "label": STATUS_LABELS[c], "canon": c}
        for c in STATUS_ALIASES
    ]
    out.append(_unknown_item())
    out.append(_none_item("Нет статуса"))
    return out


def priorities_for_ui(unknown=None):
    out = [
        {"id": PRIORITY_IDS[c], "label": PRIORITY_LABELS[c], "canon": c}
        for c in PRIORITY_ALIASES
    ]
    out.append(_unknown_item())
    out.append(_none_item("Нет приоритета"))
    return out


def projects_for_ui(raw, unknown=None):
    out = []
    for rec in _iter_records(raw):
        if not isinstance(rec, dict):
            continue
        pid = rec.get("id")
        if pid is None:
            continue
        label = rec.get("title") or rec.get("name") or rec.get("slug") or str(pid)
        out.append({"id": _to_int_id(pid), "label": label})
    out.append(_unknown_item())
    out.append(_none_item("Нет проекта"))
    # "сырые неизвестные" проекты НЕ отдаём (help-center, витрина и т.п.)
    return out


def users_for_ui(raw, unknown=None, only_active=True):
    out = []
    for rec in _iter_records(raw):
        if not isinstance(rec, dict):
            continue
        if only_active and rec.get("active") is False:
            continue
        uid = rec.get("id")
        if uid is None:
            continue
        label = rec.get("name") or rec.get("display_name") or rec.get("login") or str(uid)
        out.append({"id": _to_int_id(uid), "label": label})
    out.append(_unknown_item())
    out.append(_none_item("Нет исполнителя"))
    return out


def tags_for_ui(tasks):
    seen = set()
    for t in tasks:
        for tag in t.get("tags") or []:
            s = str(tag).strip()
            if s:
                seen.add(s)
    out = [{"id": _to_int_id(t), "label": t} for t in sorted(seen)]
    out.append(_none_item("Нет тегов"))
    return out


def sort_for_ui():
    return {
        "fields": [
            {"id": "created",  "label": "Дата создания"},
            {"id": "due",      "label": "Срок"},
            {"id": "estimate", "label": "Оценка (часы)"},
        ],
        "directions": [
            {"id": "asc",  "label": "По возрастанию"},
            {"id": "desc", "label": "По убыванию"},
        ],
    }