"""
Tests for qrsip.logging — structured logging (NFR-004, spec 38).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from io import StringIO

import pytest

from qrsip.logging import (
    HumanFormatter,
    StructuredFormatter,
    configure_logging,
    get_logger,
    log_event,
    timed_event,
)


@pytest.fixture
def isolated_logger() -> Iterator[tuple[logging.Logger, StringIO]]:
    """Provide an isolated logger + stream with guaranteed cleanup."""
    logger = logging.getLogger("qrsip.test.isolated")
    logger.setLevel(logging.DEBUG)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    try:
        yield logger, stream
    finally:
        logger.removeHandler(handler)


class TestStructuredFormatter:
    def test_formats_as_json(self) -> None:
        fmt = StructuredFormatter(service="qrsip")
        logger = logging.getLogger("qrsip.test")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        logger.info("hello world", extra={"experiment_id": "EXP-0001"})

        line = stream.getvalue().strip()
        payload = json.loads(line)
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["service"] == "qrsip"
        assert payload["experiment_id"] == "EXP-0001"

    def test_includes_extra_context(self) -> None:
        fmt = StructuredFormatter()
        logger = logging.getLogger("qrsip.test")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        logger.info("event", extra={"custom": 42})

        line = stream.getvalue().strip()
        payload = json.loads(line)
        assert payload["context"]["custom"] == 42

    def test_does_not_duplicate_canonical_fields_in_context(self) -> None:
        fmt = StructuredFormatter()
        logger = logging.getLogger("qrsip.test")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        # event_type is a canonical field. Passing it in extra should not
        # cause it to appear in the context section.
        logger.info("event", extra={"event_type": "custom", "extra": "y"})

        line = stream.getvalue().strip()
        payload = json.loads(line)
        # Canonical fields should not be duplicated in context.
        assert "event_type" not in payload.get("context", {})
        assert payload["context"]["extra"] == "y"


class TestHumanFormatter:
    def test_formats_compact_human_readable(self) -> None:
        fmt = HumanFormatter()
        logger = logging.getLogger("qrsip.test")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        logger.info("hello")

        line = stream.getvalue().strip()
        assert "INFO" in line
        assert "hello" in line


class TestConfigureLogging:
    def test_configures_root_logger(self) -> None:
        configure_logging(level=logging.WARNING)
        root = logging.getLogger("qrsip")
        assert root.level == logging.WARNING

    def test_idempotent_reconfiguration(self) -> None:
        configure_logging(level=logging.INFO)
        first_handlers = list(logging.getLogger("qrsip").handlers)
        configure_logging(level=logging.WARNING)
        second_handlers = list(logging.getLogger("qrsip").handlers)
        assert len(first_handlers) == len(second_handlers) == 1


class TestGetLogger:
    def test_returns_qrsip_logger(self) -> None:
        logger = get_logger("qrsip")
        assert logger.name == "qrsip"

    def test_prefixed_logger_lives_in_qrsip_namespace(self) -> None:
        logger = get_logger("strategy")
        assert logger.name == "qrsip.strategy"


class TestLogEvent:
    def test_emits_structured_event(self) -> None:
        fmt = StructuredFormatter()
        logger = logging.getLogger("qrsip.test")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        log_event(
            logger,
            logging.INFO,
            "experiment.run",
            "started",
            experiment_id="EXP-0001",
            run_id="RUN-0001",
            status="ok",
        )

        line = stream.getvalue().strip()
        payload = json.loads(line)
        assert payload["event_type"] == "experiment.run"
        assert payload["experiment_id"] == "EXP-0001"
        assert payload["run_id"] == "RUN-0001"
        assert payload["status"] == "ok"


class TestTimedEvent:
    def test_emits_completion_event(self) -> None:
        fmt = StructuredFormatter()
        logger = logging.getLogger("qrsip.test.timed_ok")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        try:
            with timed_event(logger, "experiment.run", "running", experiment_id="EXP-0001"):
                pass
        finally:
            logger.removeHandler(handler)

        line = stream.getvalue().strip()
        payload = json.loads(line)
        assert payload["event_type"] == "experiment.run"
        assert payload["status"] == "ok"
        assert payload["duration_ms"] is not None
        assert payload["experiment_id"] == "EXP-0001"

    def test_emits_error_event_on_exception(self) -> None:
        fmt = StructuredFormatter()
        logger = logging.getLogger("qrsip.test.timed_err")
        logger.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        try:
            with (
                pytest.raises(RuntimeError, match="boom"),
                timed_event(logger, "experiment.run", "running", experiment_id="EXP-0001"),
            ):
                raise RuntimeError("boom")
        finally:
            logger.removeHandler(handler)

        lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
        assert len(lines) >= 1
        error_payload = json.loads(lines[-1])
        assert error_payload["status"] == "error"
        assert error_payload["event_type"] == "experiment.run"
