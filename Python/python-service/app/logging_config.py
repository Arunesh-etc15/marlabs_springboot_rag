"""Write service and Uvicorn errors to a rotating file in the application root."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ROOT


LOGGER_NAMES = ("policy_service", "uvicorn.error")


def configure_logging(path=None):
    """Attach one shared file handler, without duplicating handlers on reload."""
    log_path = Path(path or ROOT / "service.log").resolve()
    loggers = [logging.getLogger(name) for name in LOGGER_NAMES]
    owned_handlers = set()
    for logger in loggers:
        for handler in logger.handlers:
            if getattr(handler, "policy_service_file", False):
                owned_handlers.add(handler)

    handler = None
    for existing in owned_handlers:
        if Path(existing.baseFilename) == log_path:
            handler = existing
            break

    # Only replace handlers installed by this function; keep Uvicorn's console logs.
    for existing in owned_handlers:
        if existing is not handler:
            for logger in loggers:
                if existing in logger.handlers:
                    logger.removeHandler(existing)
            existing.close()

    if handler is None:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        handler.policy_service_file = True
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))

    handler.setLevel(logging.INFO)
    for logger in loggers:
        logger.setLevel(logging.INFO)
        if handler not in logger.handlers:
            logger.addHandler(handler)
    return log_path
