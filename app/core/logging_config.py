from __future__ import annotations

import logging
from logging.config import dictConfig
from pathlib import Path

from app.core.settings import settings


def setup_logging() -> None:
    log_path = Path(settings.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.LOG_LEVEL,
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": settings.LOG_LEVEL,
                    "formatter": "standard",
                    "filename": str(log_path),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 3,
                    "encoding": "utf-8",
                },
            },
            "root": {
                "level": settings.LOG_LEVEL,
                "handlers": ["console", "file"],
            },
        }
    )
    logging.getLogger(__name__).info("Logging configured: level=%s file=%s", settings.LOG_LEVEL, log_path)
