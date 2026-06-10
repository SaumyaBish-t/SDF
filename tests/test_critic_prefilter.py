"""Tests for pipeline.critic_prefilter."""
from __future__ import annotations

import json
from itertools import islice
from types import SimpleNamespace

import pytest

import config
from models import RawExample
from pipeline import critic_prefilter as cp


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _ex(i: int, instruction: str = "what?", response: str = "answer.") -> RawExample:
    return RawExample(
        example_id=f"ex-{i}",
        node_id=f"node-{i}",
        prompt=instruction,
        completion=response,
        generator_model=config.GENERATOR_KEY.model,
        generator_key="KEY_1",
    )


def _batch(n: int = 3) -> list[RawExample]:
    return [_ex(i) for i in range(n)]


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
    monkeypatch.setattr(cp, "_make_client", lambda _ak: fake)
    async def _no_sleep(_d: float) -> None:
        return None
    monkeypatch.setattr("utils.asyncio.sleep", _no_sleep)
    return fake


# ---------------------------------------------------------------------------
# build_prefilter_prompt
# ---------------------------------------------------------------------------
def test_prompt_includes_domain_and_every_example() -> None:
    examples = [_ex(0, "q-zero", "a-zero"), _ex(1, "q-one", "a-one")]
    prompt = cp.build_prefilter_prompt(examples, domain="customer_support")
    assert "customer_support" in prompt
    assert "q-zero" in prompt and "a-zero" in prompt
    assert "q-one" in prompt and "a-one" in prompt
    assert '"id": 0' in prompt and '"id": 1' in prompt
    assert "no markdown" in prompt.lower()


# ---------------------------------------------------------------------------
# parse_prefilter_response
# ---------------------------------------------------------------------------
def test_parse_clean_response() -> None:
    text = json.dumps([{"id": 0, "pass": True}, {"id": 1, "pass": False}])
    assert cp.parse_prefilter_response(text, batch_len=2) == {0: True, 1: False}


def test_parse_accepts_int_pass_values() -> None:
    text = json.dumps([{"id": 0, "pass": 1}, {"id": 1, "pass": 0}])
    assert cp.parse_prefilter_response(text, batch_len=2) == {0: True, 1: False}


def test_parse_drops_ids_out_of_range() -> None:
    text = json.dumps([{"id": 0, "pass": True}, {"id": 99, "pass": True}])
    assert cp.parse_prefilter_response(text, batch_len=2) == {0: True}


def test_parse_drops_malformed_items() -> None:
    text = json.dumps([
        {"id": 0, "pass": True},
        {"no_id_field": True},
        {"id": 1, "pass": "maybe"},
        "string-item",
    ])
    assert cp.parse_prefilter_response(text, batch_len=3) == {0: True}


def test_parse_handles_chatty_wrapper() -> None:
    text = 'Here you go: [{"id":0,"pass":true}] enjoy.'
    assert cp.parse_prefilter_response(text, batch_len=1) == {0: True}


def test_parse_returns_empty_on_garbage() -> None:
    assert cp.parse_prefilter_response("nope", batch_len=3) == {}


# ---------------------------------------------------------------------------
# round_robin_prefilter_keys
# ---------------------------------------------------------------------------
def test_round_robin_cycles_prefilter_keys() -> None:
    pool = list(config.PRE_FILTER_KEYS)
    n = len(pool)
    keys = list(islice(cp.round_robin_prefilter_keys(), n * 2))
    assert keys == pool * 2


# ---------------------------------------------------------------------------
# prefilter_batch — mocked
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prefilter_batch_assigns_scores_in_input_order(monkeypatch) -> None:
    payload = json.dumps([
        {"id": 0, "pass": True},
        {"id": 1, "pass": False},
        {"id": 2, "pass": True},
    ])
    _install_fake(monkeypatch, payload)

    pf_key = config.PRE_FILTER_KEYS[0]
    scored = await cp.prefilter_batch(_batch(3), domain="customer_support", key=pf_key)
    assert [s.prefilter_score for s in scored] == [
        config.PREFILTER_PASS_SCORE,
        config.PREFILTER_FAIL_SCORE,
        config.PREFILTER_PASS_SCORE,
    ]
    assert [s.prefilter_key for s in scored] == ["PREFILTER_0"] * 3
    assert [s.prefilter_model for s in scored] == [pf_key.model] * 3
    # RawExample reference preserved (not copied/mutated).
    assert scored[0].raw.example_id == "ex-0"


@pytest.mark.asyncio
async def test_prefilter_missing_verdicts_become_fail(monkeypatch) -> None:
    # critic only judges id=1, omits 0 and 2
    payload = json.dumps([{"id": 1, "pass": True}])
    _install_fake(monkeypatch, payload)

    pf_key = config.PRE_FILTER_KEYS[0]
    scored = await cp.prefilter_batch(_batch(3), domain="d", key=pf_key)
    assert [s.prefilter_score for s in scored] == [
        config.PREFILTER_FAIL_SCORE,
        config.PREFILTER_PASS_SCORE,
        config.PREFILTER_FAIL_SCORE,
    ]
    assert all(s.prefilter_key == "PREFILTER_0" for s in scored)


@pytest.mark.asyncio
async def test_prefilter_unparseable_response_marks_all_fail(monkeypatch) -> None:
    _install_fake(monkeypatch, "I refuse to follow the format")
    scored = await cp.prefilter_batch(_batch(2), domain="d")
    assert all(s.prefilter_score == config.PREFILTER_FAIL_SCORE for s in scored)


@pytest.mark.asyncio
async def test_prefilter_uses_low_temperature(monkeypatch) -> None:
    payload = json.dumps([{"id": 0, "pass": True}])
    fake = _install_fake(monkeypatch, payload)
    await cp.prefilter_batch(_batch(1), domain="d", key=config.PREFILTER_KEY)
    assert fake.chat.completions.last_kwargs["temperature"] == config.PREFILTER_TEMPERATURE
    assert fake.chat.completions.last_kwargs["model"] == config.PREFILTER_KEY.model
    assert fake.chat.completions.last_kwargs["max_tokens"] == config.PREFILTER_MAX_TOKENS


@pytest.mark.asyncio
async def test_prefilter_empty_input_short_circuits(monkeypatch) -> None:
    fake = _install_fake(monkeypatch, "")
    assert await cp.prefilter_batch([], domain="d") == []
    assert fake.chat.completions.calls == 0  # never called the API


@pytest.mark.asyncio
async def test_prefilter_defaults_to_first_pool_key(monkeypatch) -> None:
    payload = json.dumps([{"id": 0, "pass": True}])
    _install_fake(monkeypatch, payload)
    scored = await cp.prefilter_batch(_batch(1), domain="d")
    assert scored[0].prefilter_model == config.PRE_FILTER_KEYS[0].model


@pytest.mark.asyncio
async def test_prefilter_rejects_non_prefilter_key(monkeypatch) -> None:
    _install_fake(monkeypatch, "[]")
    with pytest.raises(ValueError, match="not a pre-filter key"):
        await cp.prefilter_batch(_batch(1), domain="d", key=config.GENERATOR_KEY)


# ---------------------------------------------------------------------------
# filter_passing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_filter_passing_keeps_only_pass(monkeypatch) -> None:
    payload = json.dumps([
        {"id": 0, "pass": True},
        {"id": 1, "pass": False},
        {"id": 2, "pass": True},
    ])
    _install_fake(monkeypatch, payload)
    scored = await cp.prefilter_batch(_batch(3), domain="d", key=config.PREFILTER_KEY)
    survivors = cp.filter_passing(scored)
    assert len(survivors) == 2
    assert all(s.prefilter_score == config.PREFILTER_PASS_SCORE for s in survivors)
