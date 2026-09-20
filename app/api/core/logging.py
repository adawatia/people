"""Centralised logging configuration (12-factor / industry standard)."""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from pathlib import Path

_configured = False


class JsonFormatter(logging.Formatter):
    """Minimal structured JSON formatter for stdout / file sinks."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "event",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_ip",
            "user_agent",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _resolve_log_file(settings) -> Path | None:
    if not settings.log_to_file:
        return None
    log_dir = Path(settings.log_dir)
    if not log_dir.is_absolute():
        # Resolved relative to the API package so prod deployments get a
        # stable location; dev keeps file logging OFF by default so this
        # path is never written under the `fastapi dev` watcher.
        log_dir = Path(__file__).resolve().parent.parent / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / settings.log_file_name


def setup_logging(settings=None) -> logging.Logger:
    """Configure root + ``hrms`` + uvicorn loggers. Idempotent on reload."""
    global _configured

    if settings is None:
        from core.settings import get_settings

        settings = get_settings()

    level = str(getattr(settings, "log_level", "INFO") or "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = "INFO"

    environment = str(getattr(settings, "environment", "development") or "development").lower()
    log_format = str(getattr(settings, "log_format", "") or "").lower() or os.getenv(
        "LOG_FORMAT", "json" if environment == "production" else "console"
    ).lower()

    console_formatter = "json" if log_format == "json" else "console"
    handlers: list[str] = ["console"]

    handler_cfg: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": console_formatter,
            "stream": "ext://sys.stdout",
        },
    }

    log_file = _resolve_log_file(settings)
    if log_file is not None:
        handlers.append("file")
        handler_cfg["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": str(log_file),
            "encoding": "utf-8",
            "maxBytes": int(getattr(settings, "log_file_max_bytes", 10 * 1024 * 1024)),
            "backupCount": int(getattr(settings, "log_file_backup_count", 5)),
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": JsonFormatter},
            "console": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": handler_cfg,
        "root": {"handlers": handlers, "level": level},
        "loggers": {
            "hrms": {"handlers": handlers, "level": level, "propagate": False},
            # Keep uvicorn output consistent with our sinks; do not duplicate.
            "uvicorn": {"handlers": handlers, "level": level, "propagate": False},
            "uvicorn.error": {"handlers": handlers, "level": level, "propagate": False},
            "uvicorn.access": {"handlers": handlers, "level": level, "propagate": False},
            # Watchfiles reports every reload; INFO is pure noise in dev.
            "watchfiles.main": {"handlers": handlers, "level": "WARNING", "propagate": False},
        },
    }

    # dictConfig on every reload would duplicate FileHandler writes; only
    # re-apply when the sink set actually changed (first import vs reload).
    if not _configured:
        logging.config.dictConfig(config)
        _configured = True
    else:
        # Still honour level changes without adding duplicate handlers.
        logging.getLogger().setLevel(level)
        logging.getLogger("hrms").setLevel(level)

    return logging.getLogger("hrms")


def get_logger(name: str = "hrms") -> logging.Logger:
    return logging.getLogger(name)
