"""Central application logging: rotating file handler with optional console."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

from .config import BACKEND_DIR, settings
from .platform_audit import APP_NAME, get_request_id, user_id_var

_CONFIGURED = False


def _resolve_log_path() -> Path:
    raw = str(settings.log_file or "logs/backend.log").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _parse_level(name: str, default: int = logging.INFO) -> int:
    if not name:
        return default
    return getattr(logging, str(name).upper(), default)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "app": APP_NAME,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id() or None,
            "user_id": user_id_var.get() or None,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextLogFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )


def build_log_formatter() -> logging.Formatter:
    if str(settings.log_format).lower() == "json":
        return JsonLogFormatter()
    return TextLogFormatter()


def configure_application_logging(*, force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(_parse_level(settings.log_level, logging.INFO))

    formatter = build_log_formatter()
    log_path = _resolve_log_path()
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=int(settings.log_max_bytes),
        backupCount=int(settings.log_backup_count),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if settings.log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "Application logging configured | file=%s format=%s level=%s console=%s",
        log_path,
        settings.log_format,
        settings.log_level,
        settings.log_to_console,
    )
