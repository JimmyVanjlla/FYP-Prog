"""
Centralized logging setup. Previously only the Celery tasks logged anything
(see app/tasks/*.py) — the API layer had no structured logging at all, so
an unhandled exception in a route left no trace anywhere once the terminal
scrollback was gone. configure_logging() gives every module a consistent,
leveled, timestamped format via the standard `logging` module; main.py's
global exception handler (see app/main.py) is what actually uses it for
unhandled errors.
"""
import logging
import sys

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
