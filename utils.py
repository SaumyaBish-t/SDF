"""Cross-cutting helpers — retry/backoff wrapper and logging setup.

Pipeline stages import `with_retry` instead of writing their own try/except
loops, so retry policy stays consistent with config.MAX_RETRIES /
config.BACKOFF_BASE_SECONDS.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, TypeVar

import config

T = TypeVar("T")


def setup_logging() -> logging.Logger:
    """Configure the root logger to write to config.LOG_FILE."""
    raise NotImplementedError


async def with_retry(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run an async API call with exponential backoff (config.MAX_RETRIES)."""
    raise NotImplementedError
