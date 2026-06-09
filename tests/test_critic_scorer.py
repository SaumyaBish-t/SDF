"""Tests for pipeline.critic_scorer — rubric parse, composite, verdict, full_score."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import config
from models import RawExample, ScoredExample
from pipeline import critic_scorer as cs


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _raw(i: int = 0) -> RawExample:
    return RawExample(
        example_id=f"ex-{i}",
        node_id=f"node-{i}",
        prompt="What is the refund policy?",
        completion="Within 30 days of purchase.",
        generator_model=config.KEY_1.model,
        generator_key="KEY_1",
    )


def _scored(i: int = 0) -> ScoredExample:
    return ScoredExample(
        raw=_raw(i),
        prefilter_score=config.PREFILTER_PASS_SCORE,
        prefilter_model=config.KEY_3.model,
        prefilter_key="KEY_3",
    )


class _FakeChat:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.payload))]
        )


class _FakeClient:
    def __init__(self, payload: str):
        self.chat = SimpleNamespace(completions=_FakeChat(payload))


def _install_fake(monkeypatch, payload: str) -> _FakeClient:
    fake = _FakeClient(payload)
    monkeypatch.setattr(cs, "_make_client", lambda _ak: fake)
    async def _no_sleep(_d: float) -> None:
        return None
    monkeypatch.setattr("utils.asyncio.sleep", _no_sleep)
    return fake


# ---------------------------------------------------------------------------
# build_scorer_prompt
# ---------------------------------------------------------------------------
def test_prompt_includes_all_rubric_dimensions_and_example_text() -> None:
    prompt = cs.build_scorer_prompt(_scored(), domain="customer_support")
    assert "customer_support" in prompt
    for dim in config.RUBRIC_DIMENSIONS:
        assert dim in prompt
    assert "What is the refund policy?" in prompt
    assert "Within 30 days of purchase." in prompt
    assert "no markdown" in prompt.lower()


# ---------------------------------------------------------------------------
# parse_rubric
# ---------------------------------------------------------------------------
def test_parse_clean_rubric_returns_all_dims() -> None:
    payload = json.dumps({d: 4 for d in config.RUBRIC_DIMENSIONS})
    parsed = cs.parse_rubric(payload)
    assert parsed == {d: 4 for d in config.RUBRIC_DIMENSIONS}


def test_parse_strips_fences_and_chatty_prose() -> None:
    payload = (
        'Here is the rubric:\n```json\n{"factuality": 5, "instruction_clarity": 4, '
        '"response_quality": 4, "domain_relevance": 5, "format_compliance": 5}\n```'
    )
    parsed = cs.parse_rubric(payload)
    assert parsed["factuality"] == 5 and parsed["format_compliance"] == 5


def test_parse_clamps_scores_into_range() -> None:
    payload = json.dumps({
        "factuality": 99, "instruction_clarity": -3, "response_quality": 5,
        "domain_relevance": 0, "format_compliance": 2,
    })
    parsed = cs.parse_rubric(payload)
    assert parsed["factuality"] == config.RUBRIC_SCORE_MAX  # 5
    assert parsed["instruction_clarity"] == config.RUBRIC_SCORE_MIN  # 1
    assert parsed["domain_relevance"] == config.RUBRIC_SCORE_MIN
    assert parsed["response_quality"] == 5
    assert parsed["format_compliance"] == 2


def test_parse_rounds_float_scores() -> None:
    payload = json.dumps({"factuality": 3.7, "instruction_clarity": 3.4})
    parsed = cs.parse_rubric(payload)
    assert parsed["factuality"] == 4
    assert parsed["instruction_clarity"] == 3


def test_parse_drops_non_numeric_and_bool_scores() -> None:
    payload = json.dumps({
        "factuality": "good",
        "instruction_clarity": True,    # bool is subclass of int — must be excluded
        "response_quality": 4,
    })
    parsed = cs.parse_rubric(payload)
    assert "factuality" not in parsed
    assert "instruction_clarity" not in parsed
    assert parsed["response_quality"] == 4


def test_parse_ignores_unknown_dimensions() -> None:
    payload = json.dumps({"factuality": 4, "bogus_dim": 5})
    parsed = cs.parse_rubric(payload)
    assert parsed == {"factuality": 4}


def test_parse_returns_empty_on_garbage() -> None:
    assert cs.parse_rubric("not json") == {}
    assert cs.parse_rubric("") == {}


def test_parse_returns_empty_when_top_level_not_object() -> None:
    assert cs.parse_rubric("[1,2,3]") == {}


def test_parse_prefers_last_json_block_for_reasoning_models() -> None:
    """Reasoning models emit thinking JSON then a final answer JSON — pick the last."""
    payload = (
        "Let me think... {\"draft\": 1, \"placeholder\": true}\n"
        "After careful analysis, my final rubric is:\n"
        "{\"factuality\": 4, \"instruction_clarity\": 5, "
        "\"response_quality\": 4, \"domain_relevance\": 5, "
        "\"format_compliance\": 5}"
    )
    parsed = cs.parse_rubric(payload)
    assert parsed == {
        "factuality": 4,
        "instruction_clarity": 5,
        "response_quality": 4,
        "domain_relevance": 5,
        "format_compliance": 5,
    }


def test_parse_handles_nested_braces_in_reasoning_trace() -> None:
    """A CoT trace with its own `{...}` snippets must not poison the parser."""
    payload = (
        "Reasoning: { \"step\": { \"observation\": \"weak factuality\" } }\n"
        "Final: {\"factuality\": 2}"
    )
    parsed = cs.parse_rubric(payload)
    assert parsed == {"factuality": 2}


def test_parse_skips_blocks_with_no_rubric_dims_and_keeps_searching() -> None:
    """A trailing block without rubric keys shouldn't shadow an earlier valid one."""
    payload = (
        '{"factuality": 3, "instruction_clarity": 4}\n'
        "And here is some metadata:\n"
        '{"author": "model", "ts": "2026-01-01"}'
    )
    parsed = cs.parse_rubric(payload)
    assert parsed == {"factuality": 3, "instruction_clarity": 4}


def test_find_balanced_objects_returns_outermost_blocks() -> None:
    blocks = cs._find_balanced_objects('prefix {"a": 1} mid {"b": {"c": 2}} tail')
    assert blocks == ['{"a": 1}', '{"b": {"c": 2}}']


# ---------------------------------------------------------------------------
# composite_score
# ---------------------------------------------------------------------------
def test_composite_with_all_fives_is_five() -> None:
    rubric = {d: 5 for d in config.RUBRIC_DIMENSIONS}
    assert cs.composite_score(rubric) == pytest.approx(5.0)


def test_composite_with_all_ones_is_one() -> None:
    rubric = {d: 1 for d in config.RUBRIC_DIMENSIONS}
    assert cs.composite_score(rubric) == pytest.approx(1.0)


def test_composite_missing_dims_count_zero() -> None:
    # Only factuality (weight 0.30) at 5; others missing → 0
    assert cs.composite_score({"factuality": 5}) == pytest.approx(1.5)


def test_composite_uses_configured_weights() -> None:
    # factuality=4 (0.30), instruction_clarity=5 (0.20), response_quality=3 (0.25),
    # domain_relevance=5 (0.15), format_compliance=5 (0.10)
    rubric = {
        "factuality": 4, "instruction_clarity": 5, "response_quality": 3,
        "domain_relevance": 5, "format_compliance": 5,
    }
    expected = 4*0.30 + 5*0.20 + 3*0.25 + 5*0.15 + 5*0.10
    assert cs.composite_score(rubric) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# verdict_for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("score,expected", [
    (5.0, "accept"),
    (3.5, "accept"),       # boundary — ACCEPT_THRESHOLD inclusive
    (3.4, "revise"),
    (3.0, "revise"),       # boundary — REVISE_RANGE[0] inclusive
    (2.99, "reject"),
    (1.0, "reject"),
    (0.0, "reject"),
])
def test_verdict_thresholds(score: float, expected: str) -> None:
    assert cs.verdict_for(score) == expected


# ---------------------------------------------------------------------------
# full_score — mocked
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_score_accepts_high_quality(monkeypatch) -> None:
    payload = json.dumps({d: 5 for d in config.RUBRIC_DIMENSIONS})
    _install_fake(monkeypatch, payload)

    judged = await cs.full_score(_scored(1), domain="customer_support")
    assert judged.verdict == "accept"
    assert judged.full_score == pytest.approx(5.0)
    assert judged.rubric == {d: 5 for d in config.RUBRIC_DIMENSIONS}
    assert judged.scored.raw.example_id == "ex-1"


@pytest.mark.asyncio
async def test_full_score_routes_borderline_to_revise(monkeypatch) -> None:
    # Need composite in [3.0, 3.4]. All 3s = 3.0.
    payload = json.dumps({d: 3 for d in config.RUBRIC_DIMENSIONS})
    _install_fake(monkeypatch, payload)
    judged = await cs.full_score(_scored(), domain="d")
    assert judged.verdict == "revise"
    assert judged.full_score == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_full_score_rejects_low(monkeypatch) -> None:
    payload = json.dumps({d: 2 for d in config.RUBRIC_DIMENSIONS})
    _install_fake(monkeypatch, payload)
    judged = await cs.full_score(_scored(), domain="d")
    assert judged.verdict == "reject"
    assert judged.full_score == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_full_score_unparseable_response_rejects(monkeypatch) -> None:
    _install_fake(monkeypatch, "I refuse to score this in the requested format.")
    judged = await cs.full_score(_scored(), domain="d")
    assert judged.verdict == "reject"
    assert judged.full_score == 0.0
    assert judged.rubric == {}


@pytest.mark.asyncio
async def test_full_score_uses_key_5_settings(monkeypatch) -> None:
    payload = json.dumps({d: 4 for d in config.RUBRIC_DIMENSIONS})
    fake = _install_fake(monkeypatch, payload)
    await cs.full_score(_scored(), domain="d")
    kwargs = fake.chat.completions.last_kwargs
    assert kwargs["model"] == config.KEY_5.model
    assert kwargs["temperature"] == config.FULL_SCORER_TEMPERATURE
    assert kwargs["max_tokens"] == config.FULL_SCORER_MAX_TOKENS


@pytest.mark.asyncio
async def test_full_score_preserves_scored_reference(monkeypatch) -> None:
    payload = json.dumps({d: 4 for d in config.RUBRIC_DIMENSIONS})
    _install_fake(monkeypatch, payload)
    inp = _scored(7)
    judged = await cs.full_score(inp, domain="d")
    # Verify the prefilter metadata survives end-to-end.
    assert judged.scored.prefilter_key == "KEY_3"
    assert judged.scored.raw.generator_key == "KEY_1"
