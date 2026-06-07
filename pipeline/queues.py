"""Typed asyncio.Queue wrappers used by the orchestrator.

Three queues correspond to the three pipeline boundaries in CLAUDE.md:
generator → pre_filter → full_scorer → deduplicator.
"""
from __future__ import annotations

import asyncio

import config
from models import RawExample, ScoredExample, JudgedExample


def make_raw_queue() -> asyncio.Queue[RawExample]:
    raise NotImplementedError


def make_scored_queue() -> asyncio.Queue[ScoredExample]:
    raise NotImplementedError


def make_accepted_queue() -> asyncio.Queue[JudgedExample]:
    raise NotImplementedError
