# -*- coding: utf-8 -*-
"""
Простейший структурный логгер.

Пишет JSON-строки в stdout. Уровни: DEBUG/INFO/WARNING/ERROR.
Формат: {"ts": "...", "level": "INFO", "logger": "...", "msg": "...", "extra": {...}}

Зачем JSON: journalctl/docker logs отдают строки, JSON парсится и грепается
(jq, grep '"level":"ERROR"'). Для тестового задания хватает.

Использование:
    from logger import get_logger
    log = get_logger("mock_server")
    log.info("server_started", port=7755)
    log.error("http_error", route="/api/v2/tasks", status=500, duration_ms=12.3)
"""

import json
import os
import sys
from datetime import datetime, timezone

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


class Logger:
    def __init__(self, name, level="INFO"):
        self.name = name
        self.level = _LEVELS.get(level.upper(), 20)

    def _log(self, level, msg, **extra):
        if _LEVELS[level] < self.level:
            return
        rec = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": level,
            "logger": self.name,
            "msg": msg,
        }
        if extra:
            rec["extra"] = extra
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def debug(self, msg, **extra):   self._log("DEBUG", msg, **extra)
    def info(self, msg, **extra):    self._log("INFO", msg, **extra)
    def warning(self, msg, **extra): self._log("WARNING", msg, **extra)
    def error(self, msg, **extra):   self._log("ERROR", msg, **extra)


def get_logger(name, level=None):
    level = level or os.environ.get("LOG_LEVEL", "INFO")
    return Logger(name, level)