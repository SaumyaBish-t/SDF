"""Generator stage — produces RawExample batches from NIM endpoints.

One call to a generator key (KEY_1=DeepSeek V4 Flash or KEY_2=GLM-4.7) returns
~batch_size training examples. The meta-prompt is built from a NodeSet so each
batch covers a specific taxonomy scenario. See PROJECT_SPEC.md §5.

The actual HTTP call is wrapped in `utils.with_retry`, so callers do not
write their own try/except. Per-key concurrency is bounded by `gen_semaphore`
to keep total in-flight requests at the value declared in `KeyRole.batch_size`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from itertools import cycle
from typing import Iterator, Optional

from openai import AsyncOpenAI

import config
from models import NodeSet, RawExample
from utils import extract_chat_content, with_retry


_log = logging.getLogger("sdf.generator")

# One semaphore per generator key — bounds in-flight requests per the key's
# batch_size budget. Keys are limited independently so a stall on KEY_1 does
# not block KEY_2. KeyRole is a frozen dataclass and therefore hashable;
# using the object itself avoids ambiguity if two roles share an api_key.
_SEMAPHORES: dict[config.KeyRole, asyncio.Semaphore] = {
    k: asyncio.Semaphore(k.batch_size) for k in config.GENERATOR_KEYS
}

_KEY_NAME: dict[config.KeyRole, str] = {
    k: f"GEN_{i}" for i, k in enumerate(config.GENERATOR_KEYS)
}


# ---------------------------------------------------------------------------
# Client factory (single seam for monkeypatching in tests)
# ---------------------------------------------------------------------------
def _make_client(key: config.KeyRole) -> AsyncOpenAI:
    # 60s timeout — without this a hung TCP connection blocks the worker
    # forever instead of erroring into with_retry's backoff loop.
    return AsyncOpenAI(base_url=key.base_url, api_key=key.api_key, timeout=60.0)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_json_array(text: str) -> list[dict]:
    """Tolerant parser for the generator's JSON-array output.

    Strips ``` fences if the model added them, attempts json.loads, then
    falls back to a greedy [...] regex match. Returns [] on total failure
    rather than raising — the orchestrator treats empty batches as a soft
    retry signal rather than a hard error.
    """
    if not text:
        return []
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(cleaned)
        return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        match = _ARRAY_RE.search(cleaned)
        if not match:
            return []
        try:
            parsed = json.loads(match.group())
            return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []


def build_meta_prompt(node_set: NodeSet, batch_size: int) -> str:
    """Render the spec §4 meta-prompt for one NodeSet + batch size."""
    dims_json = json.dumps(node_set.dimensions, ensure_ascii=False)
    return (
        f"Generate exactly {batch_size} distinct training examples for {node_set.domain} "
        f"matching this scenario: {dims_json}.\n"
        "Return ONLY a valid JSON array. No markdown, no explanation, no code fences.\n"
        '[{"instruction": "...", "response": "..."}, ...]\n'
        "Requirements:\n"
        "- Each example meaningfully different from the others\n"
        "- Vary phrasing, complexity, scenario within the node\n"
        "- No repeated sentence starters"
    )


# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------
def round_robin_keys() -> Iterator:
    """Endless cycle over (KEY_1, KEY_2). Caller picks one per batch."""
    return cycle(config.GENERATOR_KEYS)


# ---------------------------------------------------------------------------
# Core generator call
# ---------------------------------------------------------------------------
async def _raw_completion(client: AsyncOpenAI, model: str, prompt: str, temperature: float) -> str:
    """One chat completion. Isolated so `with_retry` can wrap exactly this scope."""
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=config.GEN_MAX_TOKENS,
    )
    return extract_chat_content(response)


async def generate_batch(
    node_set: NodeSet,
    key=None,
    batch_size: Optional[int] = None,
) -> list[RawExample]:
    """Produce a batch of RawExamples for one NodeSet.

    Args:
        node_set: scenario from the seed sampler.
        key: a `config.KeyRole` (one of GENERATOR_KEYS). If None, KEY_1 is used.
        batch_size: examples requested in the meta-prompt (default: GEN_DEFAULT_BATCH_SIZE).

    Empty list is returned if the model output is unparseable after retries.
    """
    selected = key if key is not None else config.GENERATOR_KEYS[0]
    bs = batch_size if batch_size is not None else config.GEN_DEFAULT_BATCH_SIZE
    if selected.model not in config.GEN_TEMPERATURE:
        raise ValueError(f"No temperature configured for generator model {selected.model!r}")
    temperature = config.GEN_TEMPERATURE[selected.model]

    prompt = build_meta_prompt(node_set, bs)
    client = _make_client(selected)
    sem = _SEMAPHORES.setdefault(selected, asyncio.Semaphore(selected.batch_size))
    key_label = _KEY_NAME.get(selected, f"GEN:{selected.model}")

    async with sem:
        text = await with_retry(
            _raw_completion,
            client,
            selected.model,
            prompt,
            temperature,
            _op_name=f"generator.{key_label}",
        )

    items = parse_json_array(text)
    if not items:
        _log.warning(
            "generator returned no parseable items (node_id=%s key=%s)",
            node_set.node_id, key_label,
        )
        return []

    examples: list[RawExample] = []
    for item in items:
        instruction = item.get("instruction") or item.get("prompt")
        response_text = item.get("response") or item.get("completion")
        if not instruction or not response_text:
            continue
        examples.append(
            RawExample(
                example_id=f"{node_set.node_id}-{uuid.uuid4().hex[:8]}",
                node_id=node_set.node_id,
                prompt=str(instruction),
                completion=str(response_text),
                generator_model=selected.model,
                generator_key=key_label,
            )
        )

    _log.info(
        "generator produced %d/%d examples (node_id=%s key=%s)",
        len(examples), bs, node_set.node_id, key_label,
    )
    return examples
