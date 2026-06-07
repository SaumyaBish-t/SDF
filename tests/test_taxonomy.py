"""Tests for taxonomy.builder + taxonomy.seed_sampler."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from taxonomy.builder import TaxonomyError, list_domains, load_taxonomy
from taxonomy.seed_sampler import CoverageError, sample_node_sets


# ---------- builder ----------

def _write_taxonomy(tmp_path: Path, name: str, content: object) -> Path:
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(content), encoding="utf-8")
    return p


def test_load_taxonomy_returns_dimensions(tmp_path: Path) -> None:
    _write_taxonomy(tmp_path, "dom", {"topic": ["a", "b"], "tone": ["x"]})
    tax = load_taxonomy("dom", domains_dir=tmp_path)
    assert tax == {"topic": ["a", "b"], "tone": ["x"]}


def test_load_taxonomy_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(TaxonomyError, match="No taxonomy file"):
        load_taxonomy("nope", domains_dir=tmp_path)


def test_load_taxonomy_invalid_json_raises(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="not valid JSON"):
        load_taxonomy("broken", domains_dir=tmp_path)


@pytest.mark.parametrize("bad", [
    [],                          # not a dict
    {},                          # empty dict
    {"topic": []},               # empty value list
    {"topic": "not-a-list"},     # value not a list
    {"topic": ["", "a"]},        # empty string value
    {"topic": ["a", 1]},         # non-string value
    {"topic": ["a", "a"]},       # duplicates
])
def test_load_taxonomy_rejects_malformed_payloads(tmp_path: Path, bad: object) -> None:
    _write_taxonomy(tmp_path, "bad", bad)
    with pytest.raises(TaxonomyError):
        load_taxonomy("bad", domains_dir=tmp_path)


def test_list_domains_returns_sorted_names(tmp_path: Path) -> None:
    _write_taxonomy(tmp_path, "zebra", {"d": ["v"]})
    _write_taxonomy(tmp_path, "alpha", {"d": ["v"]})
    assert list_domains(domains_dir=tmp_path) == ["alpha", "zebra"]


def test_default_customer_support_taxonomy_loads() -> None:
    """The shipped example file must always be valid."""
    tax = load_taxonomy("customer_support")
    assert "topic" in tax and "tone" in tax
    assert all(isinstance(v, list) and v for v in tax.values())


# ---------- sampler ----------

SMALL = {"topic": ["a", "b"], "tone": ["x", "y", "z"]}


def test_sample_node_sets_produces_n_items() -> None:
    out = sample_node_sets(SMALL, "dom", n=20, seed=1)
    assert len(out) == 20


def test_sample_node_sets_assigns_all_dimensions() -> None:
    out = sample_node_sets(SMALL, "dom", n=10, seed=1)
    for ns in out:
        assert set(ns.dimensions.keys()) == set(SMALL.keys())
        for dim, val in ns.dimensions.items():
            assert val in SMALL[dim]


def test_sample_node_sets_meets_min_coverage_per_dim() -> None:
    n, min_cov = 30, 3
    out = sample_node_sets(SMALL, "dom", n=n, min_coverage=min_cov, seed=42)
    for dim, values in SMALL.items():
        counts = Counter(ns.dimensions[dim] for ns in out)
        for v in values:
            assert counts[v] >= min_cov, f"{dim}={v} only {counts[v]} of {min_cov}"


def test_sample_node_sets_strict_raises_when_n_too_small() -> None:
    # 3 values × 3 min_coverage = 9 required for 'tone', n=5 too small.
    with pytest.raises(CoverageError):
        sample_node_sets(SMALL, "dom", n=5, min_coverage=3, seed=1)


def test_sample_node_sets_non_strict_allows_undercoverage() -> None:
    out = sample_node_sets(SMALL, "dom", n=5, min_coverage=3, seed=1, strict=False)
    assert len(out) == 5  # no crash


def test_sample_node_sets_is_deterministic_with_seed() -> None:
    a = sample_node_sets(SMALL, "dom", n=20, seed=7)
    b = sample_node_sets(SMALL, "dom", n=20, seed=7)
    assert [(ns.node_id, ns.dimensions) for ns in a] == [
        (ns.node_id, ns.dimensions) for ns in b
    ]


def test_sample_node_sets_different_seeds_differ() -> None:
    a = sample_node_sets(SMALL, "dom", n=20, seed=1)
    b = sample_node_sets(SMALL, "dom", n=20, seed=2)
    assert [ns.dimensions for ns in a] != [ns.dimensions for ns in b]


def test_sample_node_sets_node_ids_are_unique_and_contiguous() -> None:
    out = sample_node_sets(SMALL, "dom", n=15, seed=1)
    ids = [ns.node_id for ns in out]
    assert len(set(ids)) == 15
    assert ids[0] == "dom-000000" and ids[-1] == "dom-000014"


def test_sample_node_sets_rejects_zero_or_negative_n() -> None:
    with pytest.raises(ValueError):
        sample_node_sets(SMALL, "dom", n=0, seed=1)
    with pytest.raises(ValueError):
        sample_node_sets(SMALL, "dom", n=-3, seed=1)


def test_sample_node_sets_rejects_zero_min_coverage() -> None:
    with pytest.raises(ValueError):
        sample_node_sets(SMALL, "dom", n=10, min_coverage=0, seed=1)


def test_sample_node_sets_realistic_throughput() -> None:
    """Realistic call on the shipped taxonomy — 500 examples, default coverage."""
    tax = load_taxonomy("customer_support")
    out = sample_node_sets(tax, "customer_support", n=500, seed=99)
    assert len(out) == 500
    # Spot-check: most populous dim still meets coverage.
    for dim, values in tax.items():
        counts = Counter(ns.dimensions[dim] for ns in out)
        for v in values:
            assert counts[v] >= 3
