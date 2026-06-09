"""Tests for pipeline.generator — parser, meta-prompt, generate_batch (mocked)."""
from __future__ import annotations

import json
from itertools import islice
from types import SimpleNamespace
from typing import Optional

import pytest

import config
from models import NodeSet
from pipeline import generator


# ---------------------------------------------------------------------------
# parse_json_array
# ---------------------------------------------------------------------------
def test_parse_clean_array() -> None:
    text = '[{"instruction": "a", "response": "b"}]'
    assert generator.parse_json_array(text) == [{"instruction": "a", "response": "b"}]


def test_parse_strips_markdown_fences() -> None:
    text = '```json\n[{"x": 1}]\n```'
    assert generator.parse_json_array(text) == [{"x": 1}]


def test_parse_recovers_from_chatty_prefix() -> None:
    text = 'Sure! Here are the examples:\n[{"x": 1}, {"x": 2}]\nLet me know.'
    assert generator.parse_json_array(text) == [{"x": 1}, {"x": 2}]


def test_parse_returns_empty_on_garbage() -> None:
    assert generator.parse_json_array("totally not json") == []
    assert generator.parse_json_array("") == []


def test_parse_drops_non_dict_items() -> None:
    text = '[{"ok": 1}, "string", 42, {"also": 2}]'
    assert generator.parse_json_array(text) == [{"ok": 1}, {"also": 2}]


def test_parse_returns_empty_when_top_level_not_array() -> None:
    assert generator.parse_json_array('{"not": "array"}') == []


# ---------------------------------------------------------------------------
# build_meta_prompt
# ---------------------------------------------------------------------------
def test_meta_prompt_includes_batch_size_domain_and_dimensions() -> None:
    ns = NodeSet(
        node_id="cs-0",
        domain="customer_support",
        dimensions={"topic": "billing_dispute", "tone": "frustrated"},
    )
    prompt = generator.build_meta_prompt(ns, batch_size=7)
    assert "Generate exactly 7" in prompt
    assert "customer_support" in prompt
    assert "billing_dispute" in prompt
    assert "frustrated" in prompt
    # Forbidden output forms must be called out.
    assert "no markdown" in prompt.lower()


# ---------------------------------------------------------------------------
# round_robin_keys
# ---------------------------------------------------------------------------
def test_round_robin_keys_cycles_generator_keys() -> None:
    pool = list(config.GENERATOR_KEYS)
    cyc = generator.round_robin_keys()
    seen = list(islice(cyc, len(pool) * 2))
    assert seen == pool * 2


# ---------------------------------------------------------------------------
# generate_batch — mocked AsyncOpenAI
# ---------------------------------------------------------------------------
class _FakeChat:
    def __init__(self, payload: str, fail_times: int = 0):
        self._payload = payload
        self._fail_times = fail_times
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError(f"transient failure {self.calls}")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._payload))]
        )


class _FakeClient:
    def __init__(self, payload: str, fail_times: int = 0):
        self.chat = SimpleNamespace(completions=_FakeChat(payload, fail_times))


def _install_fake_client(monkeypatch, payload: str, fail_times: int = 0) -> _FakeClient:
    fake = _FakeClient(payload, fail_times)
    monkeypatch.setattr(generator, "_make_client", lambda _api_key: fake)
    # Skip backoff sleeps during retries.
    async def _no_sleep(_d: float) -> None:
        return None
    monkeypatch.setattr("utils.asyncio.sleep", _no_sleep)
    return fake


def _ns() -> NodeSet:
    return NodeSet(
        node_id="cs-000001",
        domain="customer_support",
        dimensions={"topic": "billing_dispute", "tone": "polite"},
    )


@pytest.mark.asyncio
async def test_generate_batch_returns_typed_examples(monkeypatch) -> None:
    payload = json.dumps([
        {"instruction": "Q1?", "response": "A1."},
        {"instruction": "Q2?", "response": "A2."},
    ])
    _install_fake_client(monkeypatch, payload)

    gen_key = config.GENERATOR_KEYS[0]
    examples = await generator.generate_batch(_ns(), key=gen_key, batch_size=2)
    assert len(examples) == 2
    assert examples[0].prompt == "Q1?" and examples[0].completion == "A1."
    assert examples[0].generator_model == gen_key.model
    assert examples[0].generator_key == "GEN_0"
    assert examples[0].node_id == "cs-000001"
    assert examples[0].example_id.startswith("cs-000001-")
    # example_ids must be unique within a batch.
    assert len({e.example_id for e in examples}) == len(examples)


@pytest.mark.asyncio
async def test_generate_batch_skips_items_missing_required_fields(monkeypatch) -> None:
    payload = json.dumps([
        {"instruction": "ok", "response": "ok"},
        {"instruction": "", "response": "x"},
        {"response": "no instruction"},
        {"instruction": "no response"},
    ])
    _install_fake_client(monkeypatch, payload)
    gen_key = config.GENERATOR_KEYS[0]
    examples = await generator.generate_batch(_ns(), key=gen_key)
    assert len(examples) == 1
    assert examples[0].generator_key == "GEN_0"
    assert examples[0].generator_model == gen_key.model


@pytest.mark.asyncio
async def test_generate_batch_retries_then_succeeds(monkeypatch) -> None:
    payload = json.dumps([{"instruction": "i", "response": "r"}])
    fake = _install_fake_client(monkeypatch, payload, fail_times=2)
    examples = await generator.generate_batch(_ns(), key=config.KEY_1)
    assert len(examples) == 1
    assert fake.chat.completions.calls == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_generate_batch_returns_empty_on_unparseable_output(monkeypatch) -> None:
    _install_fake_client(monkeypatch, "no json here at all")
    examples = await generator.generate_batch(_ns(), key=config.KEY_1)
    assert examples == []


@pytest.mark.asyncio
async def test_generate_batch_defaults_to_first_pool_key(monkeypatch) -> None:
    payload = json.dumps([{"instruction": "i", "response": "r"}])
    _install_fake_client(monkeypatch, payload)
    examples = await generator.generate_batch(_ns())
    assert examples[0].generator_model == config.GENERATOR_KEYS[0].model
