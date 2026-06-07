"""Tests for the cli module — subcommand dispatch + JSON output."""
from __future__ import annotations

import json

import pytest

import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _captured(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out)


# ---------------------------------------------------------------------------
# parser shape
# ---------------------------------------------------------------------------
def test_parser_requires_subcommand(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_run_requires_domain_and_target(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["run"])


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def test_run_invokes_orchestrator_and_prints_summary(monkeypatch, capsys):
    captured_kwargs: dict = {}

    async def _stub_run(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "run_id": "run_test",
            "domain": kwargs["domain"],
            "target": kwargs["target"],
            "accepted": kwargs["target"],
            "rejected": 0,
            "last_node_idx": 9,
            "output_path": "/tmp/x.jsonl",
        }

    monkeypatch.setattr("pipeline.orchestrator.run", _stub_run)
    rc = cli.main([
        "run", "--domain", "customer_support", "--target", "10",
        "--seed", "7", "--gen-batch-size", "5", "--no-resume",
    ])
    assert rc == 0
    body = _captured(capsys)
    assert body["accepted"] == 10
    assert body["run_id"] == "run_test"
    assert captured_kwargs["domain"] == "customer_support"
    assert captured_kwargs["target"] == 10
    assert captured_kwargs["seed"] == 7
    assert captured_kwargs["gen_batch_size"] == 5
    assert captured_kwargs["resume"] is False


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def test_status_returns_payload_when_checkpoint_exists(monkeypatch, capsys):
    async def _stub_load(domain=None):
        return {"run_id": "run_xyz", "domain": domain, "accepted_count": 42}

    monkeypatch.setattr("pipeline.checkpoint.load_latest", _stub_load)
    rc = cli.main(["status", "--domain", "customer_support"])
    assert rc == 0
    body = _captured(capsys)
    assert body["accepted_count"] == 42


def test_status_returns_no_checkpoint_when_missing(monkeypatch, capsys):
    async def _stub_load(domain=None):
        return None

    monkeypatch.setattr("pipeline.checkpoint.load_latest", _stub_load)
    rc = cli.main(["status", "--domain", "customer_support"])
    assert rc == 1
    body = _captured(capsys)
    assert body["status"] == "no_checkpoint"


# ---------------------------------------------------------------------------
# list-domains
# ---------------------------------------------------------------------------
def test_list_domains(monkeypatch, capsys):
    monkeypatch.setattr("taxonomy.builder.list_domains", lambda: ["a", "b", "c"])
    rc = cli.main(["list-domains"])
    assert rc == 0
    body = _captured(capsys)
    assert body["domains"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------
class _StubStore:
    def __init__(self, counts: dict, embeddings=None):
        self._counts = counts
        self._embeddings = embeddings or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def coverage(self, domain, dimension):
        return self._counts

    async def all_embeddings(self, domain=None):
        return self._embeddings


def test_coverage_without_expected_returns_empty_gaps(monkeypatch, capsys):
    monkeypatch.setattr(
        "storage.store.Store",
        lambda: _StubStore({"a": 3, "b": 5}),
    )
    rc = cli.main(["coverage", "--domain", "d", "--dimension", "topic"])
    assert rc == 0
    body = _captured(capsys)
    assert body["counts"] == {"a": 3, "b": 5}
    assert body["gaps"] == {}


def test_coverage_with_expected_populates_gaps(monkeypatch, capsys):
    monkeypatch.setattr(
        "storage.store.Store",
        lambda: _StubStore({"a": 3, "b": 5, "c": 1}),
    )
    rc = cli.main([
        "coverage", "--domain", "d", "--dimension", "topic", "--expected", "4",
    ])
    assert rc == 0
    body = _captured(capsys)
    assert body["gaps"] == {"c": 3, "a": 1}


# ---------------------------------------------------------------------------
# diversity
# ---------------------------------------------------------------------------
def test_diversity_orthogonal_embeddings(monkeypatch, capsys):
    monkeypatch.setattr(
        "storage.store.Store",
        lambda: _StubStore({}, embeddings=[[1.0, 0.0], [0.0, 1.0]]),
    )
    rc = cli.main(["diversity", "--domain", "d"])
    assert rc == 0
    body = _captured(capsys)
    assert body["n_examples"] == 2
    assert abs(body["vendi_score"] - 2.0) < 1e-6


def test_diversity_empty_store(monkeypatch, capsys):
    monkeypatch.setattr("storage.store.Store", lambda: _StubStore({}, embeddings=[]))
    rc = cli.main(["diversity", "--domain", "d"])
    assert rc == 0
    body = _captured(capsys)
    assert body["n_examples"] == 0
    assert body["vendi_score"] == 0.0
