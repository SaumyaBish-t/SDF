"""Tests for pipeline.writer — render_record + write_jsonl."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import config
from models import AcceptedExample, JudgedExample, RawExample, ScoredExample
from pipeline import writer


def _accepted(example_id: str = "ex-1") -> AcceptedExample:
    raw = RawExample(
        example_id=example_id,
        node_id="n-0",
        prompt="Q?", completion="A.",
        generator_model=config.GENERATOR_KEY.model,
        generator_key="KEY_1",
    )
    scored = ScoredExample(
        raw=raw,
        prefilter_score=config.PREFILTER_PASS_SCORE,
        prefilter_model=config.PREFILTER_KEY.model,
        prefilter_key="KEY_3",
    )
    judged = JudgedExample(
        scored=scored,
        full_score=4.55,
        rubric={d: 4 for d in config.RUBRIC_DIMENSIONS},
        verdict="accept",
    )
    return AcceptedExample(
        judged=judged,
        embedding=[0.1] * config.EMBEDDING_DIM,
        minhash_signature=[1, 2, 3],
    )


# ---------------------------------------------------------------------------
# render_record
# ---------------------------------------------------------------------------
def test_render_record_has_hf_schema_shape() -> None:
    rec = writer.render_record(
        _accepted("ex-1"),
        {"domain": "customer_support", "topic": "billing"},
        nearest_neighbor_similarity=0.71,
        generation_pass=1,
        difficulty_level=2,
    )
    assert rec["id"] == "ex-1"
    assert rec["instruction"] == "Q?"
    assert rec["response"] == "A."
    assert rec["reasoning_trace"] is None
    md = rec["metadata"]
    assert md["taxonomy_node"] == {"domain": "customer_support", "topic": "billing"}
    assert md["generator_model"] == config.GENERATOR_KEY.model
    assert md["critic_scores"] == {d: 4 for d in config.RUBRIC_DIMENSIONS}
    assert md["composite_score"] == 4.55
    assert md["nearest_neighbor_similarity"] == 0.71
    assert md["generation_pass"] == 1
    assert md["difficulty_level"] == 2
    # ISO-like timestamp
    assert md["timestamp"].endswith("Z")


def test_render_record_uses_supplied_timestamp() -> None:
    fixed = datetime(2026, 6, 7, 14, 22, 11, tzinfo=timezone.utc)
    rec = writer.render_record(_accepted(), {"domain": "d"}, timestamp=fixed)
    assert rec["metadata"]["timestamp"] == "2026-06-07T14:22:11Z"


def test_render_record_reasoning_trace_optional() -> None:
    rec = writer.render_record(_accepted(), {"domain": "d"}, reasoning_trace="step 1...")
    assert rec["reasoning_trace"] == "step 1..."


# ---------------------------------------------------------------------------
# write_jsonl
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_jsonl_appends_one_line(tmp_path: Path) -> None:
    out = tmp_path / "subdir" / "dataset.jsonl"
    await writer.write_jsonl(_accepted("ex-1"), out, {"domain": "d"})
    await writer.write_jsonl(_accepted("ex-2"), out, {"domain": "d"})

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    recs = [json.loads(l) for l in lines]
    assert [r["id"] for r in recs] == ["ex-1", "ex-2"]
    # Each line is independently parseable (true JSONL).
    for line in lines:
        json.loads(line)


@pytest.mark.asyncio
async def test_write_jsonl_creates_parent_directories(tmp_path: Path) -> None:
    out = tmp_path / "a" / "b" / "c" / "out.jsonl"
    await writer.write_jsonl(_accepted(), out, {"domain": "d"})
    assert out.exists()


@pytest.mark.asyncio
async def test_write_jsonl_handles_unicode(tmp_path: Path) -> None:
    raw = RawExample(
        example_id="ex-hi",
        node_id="n-0",
        prompt="क्या आप मदद कर सकते हैं?",   # Hindi
        completion="हाँ, ज़रूर।",
        generator_model=config.GENERATOR_KEY.model,
        generator_key="KEY_2",
    )
    scored = ScoredExample(
        raw=raw, prefilter_score=1.0, prefilter_model=config.PREFILTER_KEY.model, prefilter_key="KEY_3",
    )
    judged = JudgedExample(
        scored=scored, full_score=4.0, rubric={d: 4 for d in config.RUBRIC_DIMENSIONS}, verdict="accept",
    )
    accepted = AcceptedExample(
        judged=judged, embedding=[0.1] * config.EMBEDDING_DIM, minhash_signature=[1],
    )
    out = tmp_path / "hi.jsonl"
    await writer.write_jsonl(accepted, out, {"domain": "support", "language": "hindi"})
    rec = json.loads(out.read_text(encoding="utf-8").strip())
    assert rec["instruction"].startswith("क्या")
