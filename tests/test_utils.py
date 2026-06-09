"""Tests for utils.with_retry and utils.setup_logging."""
from __future__ import annotations

import asyncio
import logging

import pytest

import config
import utils


@pytest.mark.asyncio
async def test_with_retry_returns_on_first_success() -> None:
    calls = 0

    async def ok() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await utils.with_retry(ok)
    assert result == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_with_retry_succeeds_after_transient_failure(monkeypatch) -> None:
    # Skip the backoff sleep so the test runs instantly.
    async def _no_sleep(_d: float) -> None:
        return None
    monkeypatch.setattr(utils.asyncio, "sleep", _no_sleep)

    calls = 0

    async def flaky() -> int:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError(f"transient {calls}")
        return 42

    result = await utils.with_retry(flaky)
    assert result == 42
    assert calls == 3


@pytest.mark.asyncio
async def test_with_retry_reraises_after_max_attempts(monkeypatch) -> None:
    async def _no_sleep(_d: float) -> None:
        return None
    monkeypatch.setattr(utils.asyncio, "sleep", _no_sleep)
    calls = 0

    async def always_fail() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await utils.with_retry(always_fail)
    assert calls == config.MAX_RETRIES


@pytest.mark.asyncio
async def test_with_retry_passes_args_and_kwargs() -> None:
    async def add(a: int, b: int, *, c: int) -> int:
        return a + b + c

    assert await utils.with_retry(add, 1, 2, c=3) == 6


def test_setup_logging_is_idempotent() -> None:
    # Reset the module-level guard + drop any handlers a prior test
    # installed on the global "sdf" logger, so we can verify idempotency
    # from a clean slate.
    logger = logging.getLogger("sdf")
    for h in list(logger.handlers):
        logger.removeHandler(h)
    utils._logger_initialized = False  # noqa: SLF001 — test access

    logger1 = utils.setup_logging(console=False)
    logger2 = utils.setup_logging(console=False)
    assert logger1 is logger2
    # Single file handler, not duplicated by repeat calls.
    handlers = [h for h in logger1.handlers if isinstance(h, logging.Handler)]
    assert len(handlers) == 1


def test_setup_logging_writes_to_log_file() -> None:
    logger = utils.setup_logging()
    logger.info("test-marker-for-pytest")
    for h in logger.handlers:
        h.flush()
    assert config.LOG_FILE.exists()
    content = config.LOG_FILE.read_text(encoding="utf-8")
    assert "test-marker-for-pytest" in content


# ---------------------------------------------------------------------------
# extract_chat_content — defensive guards around NIM choice quirks
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, choices):
        self.choices = choices


class _Choice:
    def __init__(self, message):
        self.message = message


class _Msg:
    def __init__(self, content):
        self.content = content


def test_extract_chat_content_happy_path() -> None:
    r = _Resp([_Choice(_Msg("hello"))])
    assert utils.extract_chat_content(r) == "hello"


def test_extract_chat_content_handles_none_choices() -> None:
    r = _Resp(None)
    assert utils.extract_chat_content(r) == ""


def test_extract_chat_content_handles_empty_choices() -> None:
    r = _Resp([])
    assert utils.extract_chat_content(r) == ""


def test_extract_chat_content_handles_missing_message() -> None:
    r = _Resp([_Choice(None)])
    assert utils.extract_chat_content(r) == ""


def test_extract_chat_content_handles_none_content() -> None:
    r = _Resp([_Choice(_Msg(None))])
    assert utils.extract_chat_content(r) == ""


def test_extract_chat_content_handles_missing_choices_attr() -> None:
    class _Bare:
        pass
    assert utils.extract_chat_content(_Bare()) == ""
