"""Tests for pipeline.orchestrator — end-to-end wiring with every stage stubbed.

Goal: verify the pipeline reaches `target`, drains all queues, writes JSONL,
checkpoints, and the sentinel propagation shuts down cleanly.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import config
from models import (
    AcceptedExample,
    JudgedExample,
    NodeSet,
    RawExample,
    ScoredExample,
)
from pipeline import orchestrator


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------
_DOMAIN = "customer_support"


def _make_raw(node_id: str, i: int) -> RawExample:
    return RawExample(
        example_id=f"{node_id}-{i:04x}",
        node_id=node_id,
        prompt=f"prompt for {node_id} #{i}",
        completion=f"completion for {node_id} #{i}",
        generator_model="stub-model",
        generator_key="KEY_1",
    )


async def _stub_generate_batch(node_set, key=None, batch_size=None):
    bs = batch_size or 5
    return [_make_raw(node_set.node_id, i) for i in range(bs)]


async def _stub_prefilter_batch(examples, domain, key=None):
    return [
        ScoredExample(
            raw=ex,
            prefilter_score=config.PREFILTER_PASS_SCORE,
            prefilter_model="stub-prefilter",
            prefilter_key="KEY_3",
        )
        for ex in examples
    ]


async def _stub_full_score(scored, domain):
    return JudgedExample(
        scored=scored,
        full_score=4.0,
        rubric={k: 4 for k in config.RUBRIC_DIMENSIONS},
        verdict="accept",
    )


class _StubStore:
    async def __aenter__(self):
        self.rows = []
        self.embeddings: list[list[float]] = []
        return self

    async def __aexit__(self, *exc):
        return None

    async def write(self, accepted, taxonomy_node):
        self.rows.append((accepted.judged.scored.raw.example_id, taxonomy_node))
        self.embeddings.append(list(accepted.embedding))

    async def nearest_similarity(self, embedding):
        return 0.0

    async def all_embeddings(self, domain=None):
        return list(self.embeddings)


class _StubDedup:
    def __init__(self, store, **_):
        self._store = store
        self._seen: set[str] = set()
        self.minhash_rejects = 0
        self.cosine_rejects = 0
        self.accepted = 0

    async def check(self, judged):
        ex_id = judged.scored.raw.example_id
        if ex_id in self._seen:
            self.minhash_rejects += 1
            return None
        self.accepted += 1
        return AcceptedExample(
            judged=judged,
            embedding=[0.0] * config.EMBEDDING_DIM,
            minhash_signature=[0] * config.MINHASH_NUM_PERM,
        )

    def register(self, example_id, text):
        self._seen.add(example_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def patched_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "generate_batch", _stub_generate_batch)
    monkeypatch.setattr(orchestrator, "prefilter_batch", _stub_prefilter_batch)
    monkeypatch.setattr(orchestrator, "full_score", _stub_full_score)
    monkeypatch.setattr(orchestrator, "Store", _StubStore)
    monkeypatch.setattr(orchestrator, "Deduplicator", _StubDedup)
    monkeypatch.setattr(config, "CHECKPOINT_DIR", tmp_path / "ckpts")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "out")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_reaches_target_and_writes_jsonl(patched_pipeline):
    out_path = patched_pipeline / "out.jsonl"

    summary = asyncio.run(
        orchestrator.run(
            domain=_DOMAIN,
            target=10,
            output_path=out_path,
            seed=1,
            gen_batch_size=5,
            n_scorer_workers=2,
            n_prefilter_workers=2,
            resume=False,
        )
    )

    assert summary["accepted"] >= 10
    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 10
    record = json.loads(lines[0])
    assert "id" in record and "instruction" in record and "metadata" in record
    assert record["metadata"]["taxonomy_node"]["domain"] == _DOMAIN


def test_checkpoint_written_on_completion(patched_pipeline):
    summary = asyncio.run(
        orchestrator.run(
            domain=_DOMAIN,
            target=5,
            output_path=patched_pipeline / "out.jsonl",
            seed=2,
            gen_batch_size=5,
            n_scorer_workers=1,
            n_prefilter_workers=1,
            resume=False,
        )
    )
    ckpt_files = list((patched_pipeline / "ckpts").glob("*.json"))
    assert ckpt_files, "expected at least one checkpoint file"
    payload = json.loads(ckpt_files[-1].read_text(encoding="utf-8"))
    assert payload["accepted_count"] == summary["accepted"]
    assert payload["domain"] == _DOMAIN
    # Vendi score wired in Session 13 — present on the final checkpoint.
    assert payload["vendi_score"] is not None
    assert payload["vendi_score"] >= 0.0


def test_resume_skips_completed_node_sets(patched_pipeline, monkeypatch):
    # First run reaches target.
    out1 = patched_pipeline / "run1.jsonl"
    s1 = asyncio.run(
        orchestrator.run(
            domain=_DOMAIN, target=5, output_path=out1, seed=3,
            gen_batch_size=5, n_scorer_workers=1, n_prefilter_workers=1,
            resume=False,
        )
    )
    assert s1["accepted"] >= 5

    # Second run with resume=True: already at target, returns immediately.
    out2 = patched_pipeline / "run2.jsonl"
    s2 = asyncio.run(
        orchestrator.run(
            domain=_DOMAIN, target=5, output_path=out2, seed=3,
            gen_batch_size=5, n_scorer_workers=1, n_prefilter_workers=1,
            resume=True,
        )
    )
    assert s2["accepted"] >= 5
    # No new JSONL should be written since we short-circuited.
    assert not out2.exists()
