"""Tests for pipeline.queues factories."""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

import config
from models import RawExample, ScoredExample, JudgedExample
from pipeline import queues


def _raw(i: int = 0) -> RawExample:
    return RawExample(
        example_id=f"ex-{i}",
        node_id="n-0",
        prompt="p",
        completion="c",
        generator_model="m",
        generator_key="KEY_1",
    )


def _scored(i: int = 0) -> ScoredExample:
    return ScoredExample(
        raw=_raw(i),
        prefilter_score=1.0,
        prefilter_model="m",
        prefilter_key="KEY_3",
    )


def _judged(i: int = 0) -> JudgedExample:
    return JudgedExample(
        scored=_scored(i),
        full_score=4.0,
        rubric={"factuality": 4},
        verdict="accept",
    )


def test_raw_queue_has_configured_maxsize() -> None:
    q = queues.make_raw_queue()
    assert q.maxsize == config.QUEUE_RAW_MAXSIZE


def test_scored_queue_has_configured_maxsize() -> None:
    q = queues.make_scored_queue()
    assert q.maxsize == config.QUEUE_SCORED_MAXSIZE


def test_accepted_queue_has_configured_maxsize() -> None:
    q = queues.make_accepted_queue()
    assert q.maxsize == config.QUEUE_ACCEPTED_MAXSIZE


@pytest.mark.asyncio
async def test_raw_queue_round_trips_typed_record() -> None:
    q = queues.make_raw_queue()
    item = _raw(1)
    await q.put(item)
    received = await q.get()
    assert received is item


@pytest.mark.asyncio
async def test_scored_queue_round_trips_typed_record() -> None:
    q = queues.make_scored_queue()
    await q.put(_scored(2))
    assert (await q.get()).prefilter_score == 1.0


@pytest.mark.asyncio
async def test_accepted_queue_round_trips_typed_record() -> None:
    q = queues.make_accepted_queue()
    await q.put(_judged(3))
    got = await q.get()
    assert got.verdict == "accept"


@pytest.mark.asyncio
async def test_raw_queue_applies_backpressure_when_full(monkeypatch) -> None:
    """Putting one more item than maxsize must block until a get() drains it."""
    monkeypatch.setattr(config, "QUEUE_RAW_MAXSIZE", 2)
    q = asyncio.Queue(maxsize=config.QUEUE_RAW_MAXSIZE)
    await q.put(_raw(0))
    await q.put(_raw(1))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.put(_raw(2)), timeout=0.05)
