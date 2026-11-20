# -*- coding: utf-8 -*-
"""
Минимальный реестр метрик в стиле Prometheus.

Без внешних зависимостей. Потокобезопасен. Умеет:
  - counters:  inc(name, labels, value)
  - histograms: observe(name, value, labels)  (хранит все значения, считает p50/p95/p99)
  - gauges:    set_gauge(name, fn)             (fn() -> float, вычисляется при рендере)

Отдача:
  - render()  -> Prometheus text exposition format (совместим с /metrics)
  - to_json() -> тот же набор в JSON (для фронта)

Ограничения:
  - histograms хранят все значения в памяти. Для mock-сервиса с сотнями
    запросов это ок; для продакшена нужны buckets, а не сырые значения.
  - перцентили считаются по сырым значениям, а не по buckets — точнее,
    но дороже по памяти. Осознанный выбор для тестового задания.
"""

import threading
import time
from collections import defaultdict


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self._counters = defaultdict(float)      # (name, labels_tuple) -> value
        self._histograms = defaultdict(list)     # (name, labels_tuple) -> [values]
        self._gauges = {}                        # name -> callable() -> float

    # ------------------------------------------------------------------
    # Запись
    # ------------------------------------------------------------------

    def inc(self, name, labels=None, value=1.0):
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] += value

    def observe(self, name, value, labels=None):
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._histograms[key].append(float(value))

    def set_gauge(self, name, fn):
        self._gauges[name] = fn

    # ------------------------------------------------------------------
    # Рендер: Prometheus text exposition format
    # ------------------------------------------------------------------

    def render(self):
        lines = []
        with self._lock:
            for (name, labels), val in sorted(self._counters.items()):
                lines.append(self._fmt(name, labels, val, "_total"))

            for (name, labels), values in sorted(self._histograms.items()):
                if not values:
                    continue
                s = sorted(values)
                n = len(s)
                lines.append(self._fmt(name, labels, sum(s), "_sum"))
                lines.append(self._fmt(name, labels, n, "_count"))
                for q in (0.5, 0.95, 0.99):
                    idx = min(n - 1, int(q * n))
                    lines.append(self._fmt(name, labels, s[idx], f"_p{int(q * 100)}"))

            gauge_lines = []
            for name, fn in sorted(self._gauges.items()):
                try:
                    val = fn()
                except Exception:
                    val = float("nan")
                gauge_lines.append(f"{name} {val}")
        # gauges рендерим вне lock: fn() может быть тяжёлой
        lines.extend(gauge_lines)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _fmt(name, labels, value, suffix=""):
        if labels:
            lbl = ",".join(f'{k}="{v}"' for k, v in labels)
            return f"{name}{suffix}{{{lbl}}} {value}"
        return f"{name}{suffix} {value}"

    # ------------------------------------------------------------------
    # Рендер: JSON (для фронта)
    # ------------------------------------------------------------------

    def to_json(self):
        out = {"counters": {}, "histograms": {}, "gauges": {}}
        with self._lock:
            for (name, labels), val in self._counters.items():
                out["counters"][self._key(name, labels)] = val
            for (name, labels), values in self._histograms.items():
                if not values:
                    continue
                s = sorted(values)
                n = len(s)
                out["histograms"][self._key(name, labels)] = {
                    "count": n,
                    "sum": round(sum(s), 6),
                    "p50": round(s[min(n - 1, int(0.5 * n))], 6),
                    "p95": round(s[min(n - 1, int(0.95 * n))], 6),
                    "p99": round(s[min(n - 1, int(0.99 * n))], 6),
                }
        gauge_snapshot = {}
        for name, fn in self._gauges.items():
            try:
                gauge_snapshot[name] = fn()
            except Exception:
                gauge_snapshot[name] = None
        out["gauges"] = gauge_snapshot
        return out

    @staticmethod
    def _key(name, labels):
        if not labels:
            return name
        lbl = ",".join(f"{k}={v}" for k, v in labels)
        return f"{name}{{{lbl}}}"


# Глобальный реестр. Импортируется в mock_server.py.
METRICS = Metrics()
METRICS.set_gauge("uptime_seconds", lambda: round(time.time() - METRICS.start_time, 3))