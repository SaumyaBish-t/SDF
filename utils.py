"""Cross-cutting helpers — retry/backoff wrapper and logging setup.

Pipeline stages import `with_retry` instead of writing their own try/except
loops, so retry policy stays consistent with config.MAX_RETRIES /
config.BACKOFF_BASE_SECONDS.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Awaitable, Callable, TypeVar

import config

T = TypeVar("T")

_LOGGER_NAME = "sdf"
_logger_initialized = False


def setup_logging(*, console: bool = True) -> logging.Logger:
    """Configure the 'sdf' logger.

    File handler (always): full log at config.LOG_LEVEL written to
      config.LOG_FILE (rotating, 10MB × 5 backups, UTF-8).
    Console handler (default on): INFO+ mirrored to stderr in a compact
      one-line format so CLI users see live progress instead of staring
      at a frozen prompt. Pass `console=False` for library/test use.
    Idempotent — calling multiple times does not duplicate handlers.
    """
    global _logger_initialized
    logger = logging.getLogger(_LOGGER_NAME)
    if _logger_initialized:
        return logger

    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False  # don't leak to root → duplicate output

    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    if console:
        # Compact stderr stream: timestamp + level + short name + message.
        # Goes to stderr so JSON-on-stdout from the CLI stays clean for
        # pipes (`python cli.py status | jq ...`).
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname).1s %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(stream_handler)

    _logger_initialized = True
    return logger


async def with_retry(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    _op_name: str | None = None,
    **kwargs: Any,
) -> T:
    """Run an async callable with exponential backoff.

    Policy (from config): up to MAX_RETRIES attempts, delay = BACKOFF_BASE_SECONDS ** attempt.
    Logs each failure with attempt number; re-raises the final exception.

    Use `_op_name` to label the operation in logs (defaults to the callable's name).
    """
    logger = logging.getLogger(f"{_LOGGER_NAME}.retry")
    op = _op_name or getattr(fn, "__name__", "anonymous")
    last_exc: BaseException | None = None

    for attempt in range(config.MAX_RETRIES):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — caller controls fn
            last_exc = exc
            is_last = attempt == config.MAX_RETRIES - 1
            if is_last:
                logger.error(
                    "%s failed (attempt %d/%d), giving up: %s",
                    op, attempt + 1, config.MAX_RETRIES, exc,
                )
                raise
            delay = config.BACKOFF_BASE_SECONDS ** attempt
            logger.warning(
                "%s failed (attempt %d/%d), retrying in %ds: %s",
                op, attempt + 1, config.MAX_RETRIES, delay, exc,
            )
            await asyncio.sleep(delay)

    # Unreachable — loop either returns or raises. Satisfies type checker.
    assert last_exc is not None
    raise last_exc


def extract_chat_content(response: Any) -> str:
    """Pull `choices[0].message.content` out of a chat-completion response.

    NIM occasionally returns responses where `choices` is `None`, an empty
    list, or where `message` is missing — the raw `response.choices[0]...`
    indexing path then raises `'NoneType' object is not subscriptable` and
    blows up under `with_retry`. This helper returns "" instead so the
    caller can treat the empty response as "unparseable" via its own
    fail-safe path, without burning retries on a structural quirk.

    Used by generator + critic_prefilter + critic_scorer at their single
    chat.completions.create() call sites.
    """
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None:
        return ""
    return getattr(message, "content", None) or ""
