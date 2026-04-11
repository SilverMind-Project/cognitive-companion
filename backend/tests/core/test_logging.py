"""Tests for :mod:`backend.core.logging`."""

from __future__ import annotations

import io
import logging

import pytest

from backend.core.logging import BoundLogger, get_logger, setup_logging


@pytest.fixture
def fresh_logger(request: pytest.FixtureRequest) -> BoundLogger:
    """Return a uniquely-named logger so tests don't clobber each other."""
    name = f"test.{request.node.name}"
    inner = logging.getLogger(name)
    inner.handlers.clear()
    inner.setLevel(logging.DEBUG)
    inner.propagate = True
    return BoundLogger(inner)


class TestBoundLoggerFormatting:
    def test_event_without_kwargs(
        self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger
    ) -> None:
        with caplog.at_level(logging.INFO, logger=fresh_logger._inner.name):
            fresh_logger.info("plain_event")
        assert "plain_event" in caplog.text

    def test_event_with_kwargs(
        self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger
    ) -> None:
        with caplog.at_level(logging.INFO, logger=fresh_logger._inner.name):
            fresh_logger.info("sensor", sensor_id="cam1", room="Kitchen")
        rec = caplog.records[-1]
        assert rec.getMessage() == "sensor sensor_id=cam1 room=Kitchen"

    def test_format_is_static(self) -> None:
        # _format is a pure helper — no logger instance needed.
        assert BoundLogger._format("evt", {}) == "evt"
        assert BoundLogger._format("evt", {"k": 1}) == "evt k=1"


class TestLogLevels:
    def test_debug_suppressed_below_level(
        self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger
    ) -> None:
        fresh_logger._inner.setLevel(logging.INFO)
        with caplog.at_level(logging.INFO, logger=fresh_logger._inner.name):
            fresh_logger.debug("never_emitted")
        assert "never_emitted" not in caplog.text

    def test_warning_level(
        self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=fresh_logger._inner.name):
            fresh_logger.warning("careful", code=7)
        assert "careful code=7" in caplog.text

    def test_warn_is_alias_for_warning(self, fresh_logger: BoundLogger) -> None:
        assert BoundLogger.warn is BoundLogger.warning

    def test_error_level(self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger) -> None:
        with caplog.at_level(logging.ERROR, logger=fresh_logger._inner.name):
            fresh_logger.error("bad_thing")
        assert "bad_thing" in caplog.text

    def test_critical_level(
        self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger
    ) -> None:
        with caplog.at_level(logging.CRITICAL, logger=fresh_logger._inner.name):
            fresh_logger.critical("meltdown")
        assert "meltdown" in caplog.text

    def test_exception_captures_traceback(
        self, caplog: pytest.LogCaptureFixture, fresh_logger: BoundLogger
    ) -> None:
        with caplog.at_level(logging.ERROR, logger=fresh_logger._inner.name):
            try:
                raise RuntimeError("kaboom")
            except RuntimeError:
                fresh_logger.exception("caught_it")
        rec = caplog.records[-1]
        assert rec.exc_info is not None
        assert rec.exc_info[0] is RuntimeError


class TestGetLogger:
    def test_returns_bound_logger(self) -> None:
        assert isinstance(get_logger("x.y.z"), BoundLogger)

    def test_accepts_none_name(self) -> None:
        assert isinstance(get_logger(None), BoundLogger)


class TestSetupLogging:
    def test_accepts_explicit_level_int(self) -> None:
        buf = io.StringIO()
        setup_logging(level=logging.WARNING, stream=buf)
        assert logging.getLogger().level == logging.WARNING

    def test_accepts_explicit_level_string(self) -> None:
        buf = io.StringIO()
        setup_logging(level="ERROR", stream=buf)
        assert logging.getLogger().level == logging.ERROR

    def test_silences_noisy_loggers(self) -> None:
        buf = io.StringIO()
        setup_logging(level=logging.DEBUG, stream=buf)
        for name in ("httpx", "httpcore", "urllib3", "sqlalchemy.engine"):
            assert logging.getLogger(name).level == logging.WARNING

    def test_reads_level_from_settings_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Temporarily swap in a Settings object with a known log level.
        from backend.core import config as config_module
        from backend.core.config import Settings

        fake = Settings.from_dict({"app": {"log_level": "WARNING"}})
        monkeypatch.setattr(config_module, "settings", fake)
        buf = io.StringIO()
        setup_logging(stream=buf)
        assert logging.getLogger().level == logging.WARNING
