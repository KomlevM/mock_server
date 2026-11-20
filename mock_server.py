#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальный mock API.

Запуск: python3 mock_server.py [порт]

Контракт:
  GET  /health                        -> {status, token}
  GET  /api/v2/health                 -> {status, token}
  GET  /api/v2/tasks?page=0&limit=50  -> {data, meta}
  POST /api/v2/tasks                  -> {data, meta} (фильтры/сортировка в теле)
  POST /api/v2/summary                -> счётчики по отфильтрованным задачам
  GET  /api/v2/tasks/{uuid|key|id}    -> TaskDto
  GET  /api/v2/tasks/{uuid}/comments  -> {comments, next_cursor, total}
  GET  /api/v2/filters                -> справочники для UI фильтров
  GET  /api/v2/system/pulse           -> {service, heartbeat, version, utc_time}
"""
import json
import os
import sys
import time
import threading
import math
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, unquote
from logger import get_logger
log = get_logger("mock_server")

from normalization import (
    normalize_task,
    normalize_filters,
    apply_filters,
    apply_sort,
    normalize_sort,
    compute_summary,
    build_users_index,
    build_users_meta,
    build_projects_index,
    statuses_for_ui,
    priorities_for_ui,
    projects_for_ui,
    users_for_ui,
    tags_for_ui,
    sort_for_ui,
    unknown_values_for_ui,
    FILTER_FIELDS,
    DUE_SOON_DEFAULT_DAYS, UNKNOWN,
)
from Тестовое.metrics import METRICS

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7755
HERE = os.path.dirname(os.path.abspath(__file__))

BURST_CAP = 15
RATE_WINDOW = 1.0
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
MAX_COMMENTS_LIMIT = 500
STAFF_KEY = "tb-staff-2024"

HEARTBEAT = "TB-PULSE-" + time.strftime("%Y%m%d", time.gmtime())

_req_lock = threading.Lock()
_req_times = []

_cache_lock = threading.Lock()
_cache = {}


def _load_json(name, default):
    path = os.path.join(HERE, "data", name)
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return default
    key = (path, st.st_mtime_ns, st.st_size)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    with open(path, "rb") as f:
        data = json.loads(f.read().decode("utf-8-sig"))
    with _cache_lock:
        _cache[key] = data
        for k in list(_cache):
            if k[0] == path and k != key:
                del _cache[k]
    return data


def _load_tasks():
    return _load_json("tasks.json", {"tasks": []}).get("tasks", [])


def _load_comments():
    return _load_json("comments.json", {}).get("comments", [])


def _load_reindex():
    return _load_json(
        "reindex-2026-11-10.json",
        {"skipped": [], "kept_direct_only": []},
    )


def _users_index():
    return build_users_index(_load_json("users.json", {"users": []}))


def _users_meta():
    return build_users_meta(_load_json("users.json", {"users": []}))


def _projects_index():
    return build_projects_index(_load_json("projects.json", {"projects": []}))


def _comments_by_task():
    out = {}
    for c in _load_comments():
        tid = c.get("task_id")
        tkey = c.get("task_key")
        if tid is not None:
            out.setdefault(str(tid), []).append(c)
        if tkey is not None:
            out.setdefault(str(tkey), []).append(c)
    return out


def _parse_int(value, default, lo=None, hi=None):
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


def _normalized_tasks():
    hidden = set(_load_reindex().get("kept_direct_only", []))
    raw_tasks = [t for t in _load_tasks() if t.get("id") not in hidden]
    users_idx = _users_index()
    users_meta = _users_meta()
    projects_idx = _projects_index()
    comments_idx = _comments_by_task()
    result = []
    for t in raw_tasks:
        try:
            dto = normalize_task(t, users_idx, projects_idx, comments_idx, users_meta)
        except Exception as e:
            log.error("normalize_failed", task_id=t.get("id"), error=str(e))
            continue
        for f in ("status", "priority", "project", "assignee",
                  "estimate", "created", "due"):
            if dto.get(f) == UNKNOWN:
                METRICS.inc("normalization_errors_total", {"field": f})
        result.append(dto)
    return result, users_idx, projects_idx


def _tasks_page_filtered(page, limit, filters=None, sort_field=None, sort_dir="asc"):
    if page < 0:
        page = 0
    limit = _parse_int(limit, DEFAULT_PAGE_SIZE, lo=1, hi=MAX_PAGE_SIZE)

    tasks, users_idx, projects_idx = _normalized_tasks()

    filters = normalize_filters(filters, users_idx, projects_idx)
    now = datetime.now(timezone.utc)
    tasks, applied = apply_filters(tasks, filters, now=now)

    for name in applied:
        METRICS.inc("filter_applied_total", {"name": name})
    METRICS.inc("tasks_normalized_total", value=len(tasks))

    sort_field, sort_dir = normalize_sort(sort_field, sort_dir)
    if sort_field:
        tasks = apply_sort(tasks, sort_field, sort_dir)

    total = len(tasks)
    total_pages = math.ceil(total / limit) if total else 0
    start = page * limit
    chunk = tasks[start:start + limit]

    meta = {
        "page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "filters": applied,
        "sort": {"field": sort_field, "dir": sort_dir} if sort_field else None,
    }
    return {
        "data": chunk,
        "meta": meta,
        "items": chunk,
        "page": page,
        "limit": limit,
        "total_items": total,
        "total_pages": total_pages,
    }


def _summary_payload(body):
    if not isinstance(body, dict):
        body = {}
    filters = body.get("filters")
    if filters is None:
        filters = {k: v for k, v in body.items() if k in FILTER_FIELDS}
    due_within_days = body.get("due_within_days", DUE_SOON_DEFAULT_DAYS)
    n = _parse_int(due_within_days, DUE_SOON_DEFAULT_DAYS, lo=0)
    if n is None:
        n = DUE_SOON_DEFAULT_DAYS

    tasks, users_idx, projects_idx = _normalized_tasks()

    if isinstance(filters, dict) and "due_within_days" in filters:
        filters = {k: v for k, v in filters.items() if k != "due_within_days"}

    filters = normalize_filters(filters, users_idx, projects_idx)
    now = datetime.now(timezone.utc)
    tasks, applied = apply_filters(tasks, filters, now=now)
    METRICS.inc("summary_requests_total", {"status": "ok"})
    return compute_summary(tasks, n, now=now)


def _task_detail(tid):
    data = _load_tasks()
    skipped = set(_load_reindex().get("skipped", []))
    tid_str = str(tid) if tid is not None else ""

    found = None
    try:
        tid_int = int(tid_str)
    except (TypeError, ValueError):
        tid_int = None
    if tid_int is not None:
        found = next((t for t in data if t.get("id") == tid_int), None)
    if found is None and tid_str.startswith("TB-"):
        found = next((t for t in data if t.get("key") == tid_str), None)
    if found is None:
        found = next(
            (t for t in data
             if str(t.get("uuid", "")) == tid_str
             or str(t.get("id", "")) == tid_str
             or str(t.get("key", "")) == tid_str),
            None,
        )
    if found is None or found.get("id") in skipped:
        return None

    dto = normalize_task(
        found, _users_index(), _projects_index(),
        _comments_by_task(), _users_meta(),
    )
    return found, dto


def _comments_sort_key(c):
    v = c.get("created", "")
    if isinstance(v, (int, float)):
        return (0, f"{v:020d}")
    return (1, str(v))


def _task_comments(tid, cursor=None, limit=DEFAULT_PAGE_SIZE):
    limit = _parse_int(limit, DEFAULT_PAGE_SIZE, lo=1, hi=MAX_COMMENTS_LIMIT)

    all_comments = _load_comments()
    task_comments = [
        c for c in all_comments
        if str(c.get("task_id")) == str(tid) or c.get("task_key") == str(tid)
    ]
    task_comments.sort(key=_comments_sort_key)

    total = len(task_comments)

    if cursor:
        idx = next(
            (i for i, c in enumerate(task_comments) if str(c.get("id")) == str(cursor)),
            None,
        )
        if idx is not None:
            task_comments = task_comments[idx + 1:]

    chunk = task_comments[:limit]
    next_cursor = chunk[-1]["id"] if chunk and len(task_comments) > limit else None

    return {
        "comments": chunk,
        "next_cursor": next_cursor,
        "total": total,
    }


def _filters_payload():
    tasks, users_idx, projects_idx = _normalized_tasks()
    unknown = unknown_values_for_ui(tasks, users_idx, projects_idx)

    return {
        "statuses": statuses_for_ui(unknown),
        "priorities": priorities_for_ui(unknown),
        "projects": projects_for_ui(_load_json("projects.json", {"projects": []}), unknown),
        "assignees": users_for_ui(_load_json("users.json", {"users": []}), unknown, only_active=False),
        "tags": tags_for_ui(tasks),
        "unknown": unknown,
        "archived": {
            "values": [False, True],
            "labels": {"false": "Активные", "true": "Архив"},
        },
        "due_within_days": {"min": 0, "max": 365, "default": 7, "unit": "days"},
        "sort": sort_for_ui(),
    }


def _pulse():
    return {
        "service": "taskboard-mock",
        "heartbeat": HEARTBEAT,
        "version": "0.7.0",
        "utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": METRICS.to_json(),
    }


def _health():
    return {"status": "ok", "token": HEARTBEAT}

# def _send(self, code, payload):
#     elapsed = time.monotonic() - getattr(self, "_t_start", time.monotonic())
#     route = getattr(self, "_route_name", "unknown")
#     METRICS.inc("http_requests_total",
#                 {"method": self.command, "route": route, "status": code})
#     if code >= 400:
#         METRICS.inc("http_errors_total",
#                     {"route": route, "status_class": f"{code // 100}xx"})
#     METRICS.observe("http_request_duration_seconds", elapsed, {"route": route})
#
#     body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
#     self.send_response(code)
#     self.send_header("Content-Type", "application/json; charset=utf-8")
#     self.send_header("Content-Length", str(len(body)))
#     self.send_header("X-RateLimit-Limit", str(BURST_CAP))
#     self.send_header("X-RateLimit-Remaining", str(self._remaining()))
#     self.end_headers()
#     if self.command != "HEAD":
#         self.wfile.write(body)

class Handler(BaseHTTPRequestHandler):
    server_version = "TaskBoardMock/0.7"
    protocol_version = "HTTP/1.1"

    def _read_json_body(self, max_bytes=1_000_000):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > max_bytes:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _rate_ok(self):
        now = time.monotonic()
        with _req_lock:
            _req_times[:] = [t for t in _req_times if now - t < RATE_WINDOW]
            _req_times.append(now)
            return len(_req_times) <= BURST_CAP

    def _remaining(self):
        with _req_lock:
            return max(0, BURST_CAP - len(_req_times))

    def _send(self, code, payload):
        elapsed = time.monotonic() - getattr(self, "_t_start", time.monotonic())
        route = getattr(self, "_route_name", "unknown")
        METRICS.inc("http_requests_total",
                    {"method": self.command, "route": route, "status": code})
        if code >= 400:
            METRICS.inc("http_errors_total",
                        {"route": route, "status_class": f"{code // 100}xx"})
        METRICS.observe("http_request_duration_seconds", elapsed, {"route": route})

        duration_ms = round(elapsed * 1000, 1)
        if code >= 500:
            log.error("http_server_error", route=route, status=code, duration_ms=duration_ms)
        elif code >= 400:
            log.warning("http_client_error", route=route, status=code, duration_ms=duration_ms)
        elif elapsed > 0.5:
            log.warning("slow_request", route=route, status=code, duration_ms=duration_ms)
        # 200 без медленности не логируем — для этого метрики

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-RateLimit-Limit", str(BURST_CAP))
        self.send_header("X-RateLimit-Remaining", str(self._remaining()))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _route_label(self, route):
        if route.startswith("/api/v2/tasks/") and route.endswith("/comments"):
            return "/api/v2/tasks/{id}/comments"
        if route.startswith("/api/v2/tasks/"):
            return "/api/v2/tasks/{id}"
        return route

    def _parse_url(self):
        parts = urlsplit(self.path)
        route = unquote(parts.path)
        if len(route) > 1 and route.endswith("/"):
            route = route.rstrip("/")
        params = {k: v[-1] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        return route, params

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._t_start = time.monotonic()
        if not self._rate_ok():
            METRICS.inc("rate_limit_hits_total")
            self._send(429, {"error": "too_many_requests"})
            return

        route, params = self._parse_url()
        self._route_name = self._route_label(route)

        if route in ("/metrics", "/api/v2/metrics"):
            body = METRICS.render().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if route == "/api/v2/metrics/json":
            self._send(200, METRICS.to_json())
            return

        if route in ("/health", "/api/v2/health"):
            self._send(200, _health())
            return

        if route == "/api/v2/system/pulse":
            self._send(200, _pulse())
            return

        if route == "/api/v2/filters":
            self._send(200, _filters_payload())
            return

        if route == "/api/v2/tasks":
            page = _parse_int(params.get("page"), 0, lo=0)
            limit = _parse_int(params.get("limit"), DEFAULT_PAGE_SIZE, lo=1, hi=MAX_PAGE_SIZE)
            self._send(200, _tasks_page_filtered(page, limit))
            return

        if route.startswith("/api/v2/tasks/"):
            tail = route[len("/api/v2/tasks/"):]
            if not tail:
                self._send(404, {"error": "unknown_route", "route": route})
                return
            parts = tail.split("/")
            tid = parts[0]

            if len(parts) >= 2 and parts[1] == "comments":
                cursor = params.get("cursor")
                limit = _parse_int(params.get("limit"), DEFAULT_PAGE_SIZE, lo=1, hi=MAX_COMMENTS_LIMIT)
                self._send(200, _task_comments(tid, cursor, limit))
                return

            res = _task_detail(tid)
            if res is None:
                self._send(404, {"error": "not_found", "id": tid})
                return
            raw, dto = res
            if raw.get("private") and self.headers.get("X-Staff-Key") != STAFF_KEY:
                self._send(403, {"error": "forbidden"})
                return
            self._send(200, dto)
            return

        if route == "/api/v2/users":
            self._send(200, _load_json("users.json", {"users": []}))
            return
        if route == "/api/v2/projects":
            self._send(200, _load_json("projects.json", {"projects": []}))
            return
        if route == "/api/v2/search":
            self._send(200, {"results": []})
            return

        self._send(404, {"error": "unknown_route", "route": route})

    def do_POST(self):
        self._t_start = time.monotonic()
        if not self._rate_ok():
            METRICS.inc("rate_limit_hits_total")
            self._route_name = "rate_limited"
            self._send(429, {"error": "too_many_requests"})
            return

        route, params = self._parse_url()
        self._route_name = route

        if route == "/api/v2/tasks":
            body = self._read_json_body()
            if body is None:
                body = {}
            if not isinstance(body, dict):
                self._send(400, {"error": "body_must_be_object"})
                return

            page = _parse_int(body.get("page", params.get("page")), 0, lo=0)
            limit = _parse_int(
                body.get("limit", params.get("limit")),
                DEFAULT_PAGE_SIZE, lo=1, hi=MAX_PAGE_SIZE,
            )

            filters = body.get("filters")
            if filters is None:
                filters = {k: v for k, v in body.items() if k in FILTER_FIELDS}

            sort = body.get("sort")
            if isinstance(sort, dict):
                sort_field = sort.get("field")
                sort_dir = sort.get("dir") or "asc"
            else:
                sort_field = body.get("sort") if isinstance(body.get("sort"), str) else None
                sort_dir = body.get("dir") or "asc"

            self._send(200, _tasks_page_filtered(page, limit, filters, sort_field, sort_dir))
            return

        if route == "/api/v2/summary":
            body = self._read_json_body()
            if body is None:
                body = {}
            if not isinstance(body, dict):
                self._send(400, {"error": "body_must_be_object"})
                return
            self._send(200, _summary_payload(body))
            return

        self._send(404, {"error": "unknown_route", "route": route})

    def log_message(self, fmt, *args):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sys.stderr.write(f"[mock {ts}] " + fmt % args + "\n")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    log.info("server_starting", port=PORT, burst_cap=BURST_CAP)
    print(f"mock API listening on :{PORT} (burst cap ~{BURST_CAP}/rps)")
    Server(("127.0.0.1", PORT), Handler).serve_forever()
