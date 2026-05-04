from __future__ import annotations

import atexit
import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from queue import Queue
from typing import Any, Dict

from app.core.config import settings

BASE_DIR = os.path.dirname(__file__)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")
ROOT_LOG_LEVEL = logging.WARNING
PROJECT_LOGGER_NAME = "app"


class Colors:
    RESET = "\033[0m"
    DEBUG = "\033[36m"
    INFO = "\033[32m"
    WARNING = "\033[33m"
    ERROR = "\033[31m"
    CRITICAL = "\033[1;31m"
    TIMESTAMP = "\033[96m"


LEVEL_COLORS = {
    logging.DEBUG: Colors.DEBUG,
    logging.INFO: Colors.INFO,
    logging.WARNING: Colors.WARNING,
    logging.ERROR: Colors.ERROR,
    logging.CRITICAL: Colors.CRITICAL,
}


def _relative_path(path: str) -> str:
    try:
        relative = os.path.relpath(path, BASE_DIR)
        return relative if not relative.startswith("..") else os.path.basename(path)
    except Exception:
        return os.path.basename(path)


_old_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _old_factory(*args, **kwargs)
    record.relativepath = _relative_path(record.pathname)
    return record


logging.setLogRecordFactory(_record_factory)


class UTCFormatter(logging.Formatter):
    def __init__(self, fmt_src: str, fmt_no_src: str, colorize: bool = False, **kwargs):
        super().__init__(fmt_src, **kwargs)
        self.fmt_src = fmt_src
        self.fmt_no_src = fmt_no_src
        self.colorize = colorize

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(record.msecs):03d}"
        if self.colorize:
            return f"{Colors.TIMESTAMP}{timestamp}{Colors.RESET}"
        return timestamp

    def format(self, record: logging.LogRecord) -> str:
        hide_source = getattr(record, "hide_src", False) or record.name.startswith("uvicorn.")
        original_fmt = self._style._fmt
        self._style._fmt = self.fmt_no_src if hide_source else self.fmt_src

        if self.colorize:
            original_levelname = record.levelname
            color = LEVEL_COLORS.get(record.levelno, Colors.RESET)
            record.levelname = f"{color}{record.levelname:<8}{Colors.RESET}"

        try:
            return super().format(record)
        finally:
            self._style._fmt = original_fmt
            if self.colorize:
                record.levelname = original_levelname


class StructuredJSONFormatter(logging.Formatter):
    def __init__(self, service: str, **kwargs):
        super().__init__(**kwargs)
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "service": self.service,
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "relativepath"):
            payload["source"] = f"{record.relativepath}:{record.lineno}"
        return json.dumps(payload, default=str)


FILE_FMT_SRC = "%(asctime)s | %(levelname)-8s | %(relativepath)s:%(lineno)d | %(message)s"
FILE_FMT_NOSRC = "%(asctime)s | %(levelname)-8s | %(message)s"
CON_FMT_SRC = "%(asctime)s | %(levelname)s | %(relativepath)s:%(lineno)d | %(message)s"
CON_FMT_NOSRC = "%(asctime)s | %(levelname)s | %(message)s"

file_formatter = UTCFormatter(FILE_FMT_SRC, FILE_FMT_NOSRC, colorize=False)
console_formatter = UTCFormatter(CON_FMT_SRC, CON_FMT_NOSRC, colorize=True)

file_handler = TimedRotatingFileHandler(
    filename=LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
    utc=True,
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(console_formatter)

log_queue: Queue = Queue(-1)
queue_handler = QueueHandler(log_queue)
queue_listener = QueueListener(
    log_queue,
    file_handler,
    console_handler,
    respect_handler_level=True,
)

_logging_initialized = False
_service_loggers: Dict[str, logging.Logger] = {}


def setup_logging() -> None:
    global _logging_initialized

    if _logging_initialized:
        return

    queue_listener.start()
    atexit.register(queue_listener.stop)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(ROOT_LOG_LEVEL)

    project_logger = logging.getLogger(PROJECT_LOGGER_NAME)
    project_logger.handlers.clear()
    project_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    project_logger.addHandler(queue_handler)
    project_logger.propagate = False

    for logger_name in ("uvicorn", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(queue_handler)
        logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
        logger.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.addHandler(queue_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False

    _logging_initialized = True


def get_logger(name: str | None = None) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name or PROJECT_LOGGER_NAME)


def get_service_logger(service_name: str) -> logging.Logger:
    if service_name in _service_loggers:
        return _service_loggers[service_name]

    log_file = os.path.join(LOG_DIR, f"{service_name}.log")
    json_formatter = StructuredJSONFormatter(service=service_name)

    service_file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    service_file_handler.setLevel(logging.INFO)
    service_file_handler.setFormatter(json_formatter)

    service_console_handler = logging.StreamHandler(sys.stdout)
    service_console_handler.setLevel(logging.INFO)
    service_console_handler.setFormatter(json_formatter)

    service_queue: Queue = Queue(-1)
    service_queue_handler = QueueHandler(service_queue)
    service_listener = QueueListener(
        service_queue,
        service_file_handler,
        service_console_handler,
        respect_handler_level=True,
    )
    service_listener.start()
    atexit.register(service_listener.stop)

    service_logger = logging.getLogger(service_name)
    service_logger.handlers.clear()
    service_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    service_logger.addHandler(service_queue_handler)
    service_logger.propagate = False

    _service_loggers[service_name] = service_logger
    return service_logger


logger = get_logger(PROJECT_LOGGER_NAME)
