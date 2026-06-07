"""JSONL writer — HuggingFace-compatible output per PROJECT_SPEC §9.

One line per accepted example. The schema is HF-compatible so
`datasets.load_dataset('json', data_files=...)` works out of the box.

File IO runs through `asyncio.to_thread` so the orchestrator's event loop
isn't blocked. Each call appends one line and flushes — atomic enough for
the single-writer / single-file pattern the orchestrator uses.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models import AcceptedExample


_log = logging.getLogger("sdf.writer")


def render_record(
    accepted: AcceptedExample,
    taxonomy_node: dict[str, str],
    *,
    nearest_neighbor_similarity: Optional[float] = None,
    generation_pass: int = 1,
    difficulty_level: Optional[int] = None,
    reasoning_trace: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> dict:
    """Build the HF-shaped record (pure function — easy to unit-test).

    `taxonomy_node` is the NodeSet.dimensions dict, optionally including
    `"domain"`. `nearest_neighbor_similarity` should be the value the
    deduplicator measured during its cosine check (caller threads it in).
    """
    raw = accepted.judged.scored.raw
    ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": raw.example_id,
        "instruction": raw.prompt,
        "response": raw.completion,
        "reasoning_trace": reasoning_trace,
        "metadata": {
            "taxonomy_node": taxonomy_node,
            "generator_model": raw.generator_model,
            "critic_scores": accepted.judged.rubric,
            "composite_score": accepted.judged.full_score,
            "nearest_neighbor_similarity": nearest_neighbor_similarity,
            "generation_pass": generation_pass,
            "difficulty_level": difficulty_level,
            "timestamp": ts,
        },
    }


def _append_sync(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


async def write_jsonl(
    accepted: AcceptedExample,
    path: Path,
    taxonomy_node: dict[str, str],
    *,
    nearest_neighbor_similarity: Optional[float] = None,
    generation_pass: int = 1,
    difficulty_level: Optional[int] = None,
    reasoning_trace: Optional[str] = None,
) -> None:
    """Append one HF-compatible JSONL line to `path`. Creates parent dirs."""
    record = render_record(
        accepted,
        taxonomy_node,
        nearest_neighbor_similarity=nearest_neighbor_similarity,
        generation_pass=generation_pass,
        difficulty_level=difficulty_level,
        reasoning_trace=reasoning_trace,
    )
    line = json.dumps(record, ensure_ascii=False)
    await asyncio.to_thread(_append_sync, path, line)
    _log.debug("wrote example %s to %s", record["id"], path)
