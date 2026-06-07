"""Typed asyncio.Queue wrappers used by the orchestrator.

Three queues correspond to the three pipeline boundaries in CLAUDE.md:
generator → pre_filter → full_scorer → deduplicator.

Sizes are bounded (from config.QUEUE_*_MAXSIZE) so a slow downstream stage
applies backpressure on the upstream — preventing unbounded memory growth
when the generator outruns the critics.
"""
from __future__ import annotations

import asyncio

import config
from models import JudgedExample, RawExample, ScoredExample


def make_raw_queue() -> asyncio.Queue[RawExample]:
    """Queue1 — generator → pre_filter. Bounded by QUEUE_RAW_MAXSIZE."""
    return asyncio.Queue(maxsize=config.QUEUE_RAW_MAXSIZE)


def make_scored_queue() -> asyncio.Queue[ScoredExample]:
    """Queue2 — pre_filter → full_scorer. Bounded by QUEUE_SCORED_MAXSIZE."""
    return asyncio.Queue(maxsize=config.QUEUE_SCORED_MAXSIZE)


def make_accepted_queue() -> asyncio.Queue[JudgedExample]:
    """Queue3 — full_scorer → deduplicator/writer. Bounded by QUEUE_ACCEPTED_MAXSIZE."""
    return asyncio.Queue(maxsize=config.QUEUE_ACCEPTED_MAXSIZE)
