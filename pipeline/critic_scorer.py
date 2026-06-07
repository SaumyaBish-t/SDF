"""Full scorer stage — KEY_5 (DeepSeek R1) deep rubric scoring per example.

Pre-filter survivors enter here one at a time (KEY_5 batch_size=1). The
model returns a 5-dimension 1-5 rubric; the composite score is a weighted
sum (config.RUBRIC_WEIGHTS) which decides the verdict via the
ACCEPT/REVISE/REJECT thresholds.

Failure policy: if the rubric cannot be parsed after retries, the example
is rejected with composite=0.0. Conservative — a malformed scorer output
is treated as evidence the example was unscorable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Literal, Optional

from openai import AsyncOpenAI

import config
from models import JudgedExample, ScoredExample
from utils import with_retry


_log = logging.getLogger("sdf.critic.scorer")

_KEY = config.FULL_SCORER_KEY
_SEMAPHORE = asyncio.Semaphore(_KEY.batch_size)


# ---------------------------------------------------------------------------
# Client factory (test seam)
# ---------------------------------------------------------------------------
def _make_client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=config.NIM_BASE_URL, api_key=api_key)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)


def build_scorer_prompt(scored: ScoredExample, domain: str) -> str:
    """Render the spec §6 full-scorer rubric prompt."""
    dims = ", ".join(config.RUBRIC_DIMENSIONS)
    schema = ", ".join(f'"{d}": N' for d in config.RUBRIC_DIMENSIONS)
    return (
        f"Score this {domain} training example {config.RUBRIC_SCORE_MIN}-"
        f"{config.RUBRIC_SCORE_MAX} on each dimension ({dims}).\n"
        "Return ONLY a valid JSON object — no markdown, no code fences, no prose.\n"
        f"{{{schema}}}\n\n"
        f"REJECT (score ≤ 2) if:\n"
        "- Response contains detectable factual errors\n"
        "- Instruction is ambiguous or multi-interpretable\n"
        "- Response doesn't answer the instruction\n"
        "- Example is too similar to common internet patterns\n"
        "- Format deviates from target schema\n\n"
        f"Score {config.RUBRIC_SCORE_MAX} only if: novel phrasing, correct, complete, "
        "domain-authentic, would genuinely improve model performance.\n\n"
        f"Instruction: {scored.raw.prompt}\n"
        f"Response: {scored.raw.completion}"
    )


def parse_rubric(text: str) -> dict[str, int]:
    """Extract {dimension: int_score} from a scorer response.

    Strips ``` fences, then tries strict json.loads, then falls back to a
    greedy `{...}` regex match. Scores are clamped to [RUBRIC_SCORE_MIN,
    RUBRIC_SCORE_MAX]. Missing dimensions are omitted (caller decides).
    """
    if not text:
        return {}
    cleaned = _FENCE_RE.sub("", text).strip()

    parsed: Optional[dict] = None
    try:
        candidate = json.loads(cleaned)
        if isinstance(candidate, dict):
            parsed = candidate
    except json.JSONDecodeError:
        match = _OBJECT_RE.search(cleaned)
        if match:
            try:
                candidate = json.loads(match.group())
                if isinstance(candidate, dict):
                    parsed = candidate
            except json.JSONDecodeError:
                pass

    if parsed is None:
        return {}

    out: dict[str, int] = {}
    for dim in config.RUBRIC_DIMENSIONS:
        if dim not in parsed:
            continue
        val = parsed[dim]
        if isinstance(val, bool):  # bool is subclass of int — exclude
            continue
        if not isinstance(val, (int, float)):
            continue
        clamped = max(config.RUBRIC_SCORE_MIN, min(config.RUBRIC_SCORE_MAX, int(round(val))))
        out[dim] = clamped
    return out


def composite_score(rubric: dict[str, int]) -> float:
    """Weighted sum (RUBRIC_WEIGHTS). Missing dimensions count as 0 → drags score down."""
    return float(sum(rubric.get(d, 0) * w for d, w in config.RUBRIC_WEIGHTS.items()))


def verdict_for(score: float) -> Literal["accept", "revise", "reject"]:
    """Apply thresholds: >= ACCEPT_THRESHOLD → accept, [3.0, 3.5) → revise, else reject."""
    if score >= config.ACCEPT_THRESHOLD:
        return "accept"
    revise_min, revise_max = config.REVISE_RANGE
    if revise_min <= score <= revise_max:
        return "revise"
    return "reject"


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
        max_tokens=config.FULL_SCORER_MAX_TOKENS,
    )
    return response.choices[0].message.content or ""


async def full_score(scored: ScoredExample, domain: str) -> JudgedExample:
    """Score one ScoredExample, returning the verdict-bearing JudgedExample.

    Wraps the API call in `utils.with_retry`. On total parse failure after
    retries, returns a JudgedExample with full_score=0.0, empty rubric, and
    verdict='reject' — i.e. unscorable == rejected.
    """
    client = _make_client(_KEY.api_key)
    prompt = build_scorer_prompt(scored, domain)

    async with _SEMAPHORE:
        text = await with_retry(
            _raw_completion,
            client,
            _KEY.model,
            prompt,
            config.FULL_SCORER_TEMPERATURE,
            _op_name="scorer.KEY_5",
        )

    rubric = parse_rubric(text)
    if not rubric:
        _log.warning(
            "scorer returned no parseable rubric (example_id=%s) — rejecting",
            scored.raw.example_id,
        )
        return JudgedExample(
            scored=scored, full_score=0.0, rubric={}, verdict="reject",
        )

    score = composite_score(rubric)
    decision = verdict_for(score)
    _log.info(
        "scored example_id=%s composite=%.3f verdict=%s rubric=%s",
        scored.raw.example_id, score, decision, rubric,
    )
    return JudgedExample(
        scored=scored, full_score=score, rubric=rubric, verdict=decision,
    )
