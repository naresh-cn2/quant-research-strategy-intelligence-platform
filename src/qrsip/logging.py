"""Structured logging for QRSIP (NFR-004, spec §38).

All runs emit structured logs with the canonical fields:

    timestamp, level, service, experiment_id, run_id, strategy_id,
    event_type, message, duration, status

Design rules:
- Logs are evidence, not decoration: every material event is logged with
  actionable context.
- Logs never contain secrets.
- The default format is JSON (machine-readable); a human-readable format is
  available for local development.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any, Literal

__all__ = ["TimedEvent", "configure_logging", "get_logger", "log_event", "timed_event"]

_CANONICAL_FIELDS = (
    "timestamp",
    "level",
    "service",
    "experiment_id",
    "run_id",
    "strategy_id",
    "event_type",
    "message",
    "duration_ms",
    "status",
)

_RESERVED_LOGGING_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "timestamp",
    "taskName",
}


class StructuredFormatter(logging.Formatter):
    """Format log records as single-line JSON with canonical fields."""

    def __init__(self, service: str = "qrsip") -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "experiment_id": getattr(record, "experiment_id", None),
            "run_id": getattr(record, "run_id", None),
            "strategy_id": getattr(record, "strategy_id", None),
            "event_type": getattr(record, "event_type", None),
            "message": record.getMessage(),
            "duration_ms": getattr(record, "duration_ms", None),
            "status": getattr(record, "status", None),
        }
        # Preserve any extra structured context beyond canonical fields.
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOGGING_ATTRS
            and key not in _CANONICAL_FIELDS
            and not key.startswith("_")
        }
        if extra:
            payload["context"] = extra
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


class HumanFormatter(logging.Formatter):
    """Compact human-readable format for local development."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        exp = getattr(record, "experiment_id", None) or "-"
        event = getattr(record, "event_type", None) or record.name
        return f"{ts} {record.levelname:<7} [{exp}] {event}: {record.getMessage()}"


def configure_logging(
    level: int = logging.INFO,
    *,
    human: bool = False,
    service: str = "qrsip",
    stream: Any = sys.stderr,
) -> None:
    """Configure the root QRSIP logger. Idempotent."""
    root = logging.getLogger("qrsip")
    root.setLevel(level)
    # Replace handlers on reconfiguration to keep tests/hermetic runs clean.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(HumanFormatter() if human else StructuredFormatter(service))
    root.addHandler(handler)
    root.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger inside the qrsip namespace."""
    if name is None or name == "qrsip" or name.startswith("qrsip."):
        return logging.getLogger(name or "qrsip")
    return logging.getLogger(f"qrsip.{name}")


def log_event(
    logger: logging.Logger,
    level: int,
    event_type: str,
    message: str,
    *,
    experiment_id: str | None = None,
    run_id: str | None = None,
    strategy_id: str | None = None,
    duration_ms: float | None = None,
    status: str | None = None,
    **context: Any,
) -> None:
    """Emit one structured event with canonical fields plus extra context."""
    logger.log(
        level,
        message,
        extra={
            "event_type": event_type,
            "experiment_id": experiment_id,
            "run_id": run_id,
            "strategy_id": strategy_id,
            "duration_ms": duration_ms,
            "status": status,
            **context,
        },
    )


class TimedEvent:
    """Context manager that logs an event with its duration.

    Usage:
        with TimedEvent(logger, "experiment.run", experiment_id="EXP-0001"):
            run_experiment()

    The lowercase alias :func:`timed_event` remains available for
    backward compatibility with early callers/tests.
    """

    def __init__(
        self,
        logger: logging.Logger,
        event_type: str,
        message: str | None = None,
        *,
        level: int = logging.INFO,
        **fields: Any,
    ) -> None:
        self._logger = logger
        self._event_type = event_type
        self._message = message or event_type
        self._level = level
        self._fields = fields
        self._start = 0.0

    def __enter__(self) -> TimedEvent:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        duration_ms = (time.perf_counter() - self._start) * 1000.0
        if exc is None:
            log_event(
                self._logger,
                self._level,
                self._event_type,
                self._message,
                duration_ms=round(duration_ms, 3),
                status="ok",
                **self._fields,
            )
        else:
            log_event(
                self._logger,
                logging.ERROR,
                self._event_type,
                f"{self._message} failed: {exc}",
                duration_ms=round(duration_ms, 3),
                status="error",
                error_type=type(exc).__name__,
                **self._fields,
            )
        return False  # never swallow exceptions


def timed_event(
    logger: logging.Logger,
    event_type: str,
    message: str | None = None,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> TimedEvent:
    """Backward-compatible factory returning a :class:`TimedEvent`."""
    return TimedEvent(logger, event_type, message, level=level, **fields)
