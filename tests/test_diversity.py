"""Tests for pipeline.diversity — Vendi score + coverage gaps."""
from __future__ import annotations

import math

import pytest

from pipeline.diversity import (
    compute_vendi_score,
    coverage_deficit_total,
    coverage_gaps,
)


# ---------------------------------------------------------------------------
# compute_vendi_score
# ---------------------------------------------------------------------------
def test_vendi_empty_is_zero() -> None:
    assert compute_vendi_score([]) == 0.0


def test_vendi_single_sample_is_zero() -> None:
    assert compute_vendi_score([[1.0, 0.0, 0.0]]) == 0.0


def test_vendi_identical_samples_collapse_to_one() -> None:
    # Two identical (post-normalize) vectors → effective diversity ≈ 1.0.
    score = compute_vendi_score([[1.0, 0.0], [2.0, 0.0]])
    assert math.isclose(score, 1.0, abs_tol=1e-6)


def test_vendi_orthogonal_samples_equals_n() -> None:
    # Two orthogonal vectors → effective diversity == 2.0.
    score = compute_vendi_score([[1.0, 0.0], [0.0, 1.0]])
    assert math.isclose(score, 2.0, abs_tol=1e-6)


def test_vendi_intermediate_between_1_and_n() -> None:
    # Nearly-collinear pair → between 1 and 2 (exclusive).
    score = compute_vendi_score([[1.0, 0.0], [0.95, 0.05]])
    assert 1.0 < score < 2.0


def test_vendi_handles_zero_vector_without_nan() -> None:
    score = compute_vendi_score([[0.0, 0.0], [1.0, 0.0]])
    assert not math.isnan(score)


def test_vendi_rejects_non_2d() -> None:
    with pytest.raises(ValueError):
        compute_vendi_score([1.0, 2.0, 3.0])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# coverage_gaps
# ---------------------------------------------------------------------------
def test_coverage_gaps_returns_deficits_only() -> None:
    counts = {"a": 5, "b": 10, "c": 2}
    gaps = coverage_gaps(counts, expected_per_value=8)
    assert gaps == {"c": 6, "a": 3}  # "b" excluded; sorted by deficit desc


def test_coverage_gaps_sorted_descending() -> None:
    counts = {"x": 1, "y": 4, "z": 0}
    gaps = coverage_gaps(counts, expected_per_value=5)
    assert list(gaps.keys()) == ["z", "x", "y"]


def test_coverage_gaps_empty_when_all_satisfied() -> None:
    assert coverage_gaps({"a": 10, "b": 12}, expected_per_value=5) == {}


def test_coverage_gaps_zero_expected_returns_empty() -> None:
    assert coverage_gaps({"a": 0}, expected_per_value=0) == {}


def test_coverage_deficit_total() -> None:
    assert coverage_deficit_total({"a": 5, "b": 2}, expected_per_value=8) == 9
