"""Pre-filter critic stage — cheap binary pass/fail scoring on RawExamples.

One NIM call scores a batch of examples to amortize HTTP overhead. The model
returns `[{"id": N, "pass": bool}, ...]` per spec §6. Examples missing from
the response are conservatively marked fail (treat ambiguity as rejection).

Two pre-filter keys (KEY_3=Nemotron-nano, KEY_4=Mistral Small) are rotated
round-robin. They are independent — the orchestrator just consumes whichever
finishes first. See PROJECT_SPEC.md §6 for the double-critic motivation.
"""
from __future__ import annotations

import asyncio
import json
import logging
from itertools import cycle
from typing import Iterator, Optional, Sequence

from openai import AsyncOpenAI

import config
from models import RawExample, ScoredExample
from pipeline.generator import parse_json_array  # shared tolerant parser
from utils import extract_chat_content, with_retry


_log = logging.getLogger("sdf.critic.prefilter")

_SEMAPHORES: dict[config.KeyRole, asyncio.Semaphore] = {
    k: asyncio.Semaphore(k.batch_size) for k in config.PRE_FILTER_KEYS
}

_KEY_NAME: dict[config.KeyRole, str] = {
    k: f"PREFILTER_{i}" for i, k in enumerate(config.PRE_FILTER_KEYS)
}


# ---------------------------------------------------------------------------
# Client factory (test seam)
# ---------------------------------------------------------------------------
def _make_client(key: config.KeyRole) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=key.base_url, api_key=key.api_key, timeout=60.0)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def build_prefilter_prompt(examples: Sequence[RawExample], domain: str) -> str:
    """Render the spec §6 pre-filter rubric for a batch of examples."""
    listing = "\n".join(
        json.dumps(
            {"id": i, "instruction": ex.prompt, "response": ex.completion},
            ensure_ascii=False,
        )
        for i, ex in enumerate(examples)
    )
    return (
        f"Evaluate each training example below for {domain}.\n"
        "For EACH example check ONLY:\n"
        "1. Format: is instruction non-empty? is response non-empty?\n"
        f"2. Relevance: is this clearly about {domain}?\n"
        "3. Coherence: does the response address the instruction?\n"
        "Score each 0 (fail) or 1 (pass).\n"
        'Return ONLY a valid JSON array of {"id": <int>, "pass": <bool>}.\n'
        "No markdown, no explanation, no code fences.\n\n"
        f"Examples:\n{listing}"
    )


def parse_prefilter_response(text: str, batch_len: int) -> dict[int, bool]:
    """Parse `[{"id":i,"pass":bool},...]` into {id: pass} for valid ids only.

    Tolerates extra fields, missing entries, duplicates (last wins). Drops
    items whose id is outside [0, batch_len) or whose `pass` is not bool.
    """
    parsed: dict[int, bool] = {}
    for item in parse_json_array(text):
        try:
            idx = int(item["id"])
            verdict = item["pass"]
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(verdict, bool):
            # accept 0/1 ints as fallback
            if isinstance(verdict, int) and verdict in (0, 1):
                verdict = bool(verdict)
            else:
                continue
        if 0 <= idx < batch_len:
            parsed[idx] = verdict
    return parsed


# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------
def round_robin_prefilter_keys() -> Iterator:
    """Endless cycle over (KEY_3, KEY_4)."""
    return cycle(config.PRE_FILTER_KEYS)


# ---------------------------------------------------------------------------
# Core call
# ---------------------------------------------------------------------------
async def _raw_completion(
    client: AsyncOpenAI, model: str, prompt: str, temperature: float
) -> str:
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=config.PREFILTER_MAX_TOKENS,
    )
    return extract_chat_content(response)


async def prefilter_batch(
    examples: Sequence[RawExample],
    domain: str,
    key=None,
) -> list[ScoredExample]:
    """Score a batch of RawExamples 0/1, returning one ScoredExample per input.

    Args:
        examples: batch from the generator (kept in input order in the output).
        domain: passed into the rubric prompt.
        key: KeyRole — one of PRE_FILTER_KEYS. Defaults to KEY_3.

    Examples the critic omits from its response, or for which it returns
    an unparseable verdict, are conservatively marked FAIL (score 0.0).
    """
    if not examples:
        return []
    selected = key if key is not None else config.PRE_FILTER_KEYS[0]
    if selected.name != "pre_filter":
        raise ValueError(f"{selected} is not a pre-filter key")

    prompt = build_prefilter_prompt(examples, domain)
    client = _make_client(selected)
    sem = _SEMAPHORES.setdefault(selected, asyncio.Semaphore(selected.batch_size))
    key_label = _KEY_NAME.get(selected, f"PREFILTER:{selected.model}")

    async with sem:
        text = await with_retry(
            _raw_completion,
            client,
            selected.model,
            prompt,
            config.PREFILTER_TEMPERATURE,
            _op_name=f"prefilter.{key_label}",
        )

    verdicts = parse_prefilter_response(text, batch_len=len(examples))
    if not verdicts:
        _log.warning(
            "prefilter returned no parseable verdicts (key=%s batch_size=%d)",
            key_label, len(examples),
        )

    scored: list[ScoredExample] = []
    pass_count = 0
    for idx, ex in enumerate(examples):
        passed = verdicts.get(idx, False)  # missing = fail (conservative)
        if passed:
            pass_count += 1
        scored.append(
            ScoredExample(
                raw=ex,
                prefilter_score=(
                    config.PREFILTER_PASS_SCORE if passed else config.PREFILTER_FAIL_SCORE
                ),
                prefilter_model=selected.model,
                prefilter_key=key_label,
            )
        )

    _log.info(
        "prefilter passed %d/%d (key=%s)",
        pass_count, len(examples), key_label,
    )
    return scored


def filter_passing(scored: Sequence[ScoredExample]) -> list[ScoredExample]:
    """Convenience filter — keep only items the pre-filter passed.

    Orchestrator uses this between scored_queue producers and the full_scorer.
    """
    return [s for s in scored if s.prefilter_score >= config.PREFILTER_PASS_SCORE]
