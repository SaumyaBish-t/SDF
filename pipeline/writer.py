"""JSONL writer — final HuggingFace-compatible output for accepted examples."""
from __future__ import annotations

from pathlib import Path

from models import AcceptedExample


async def write_jsonl(example: AcceptedExample, path: Path) -> None:
    raise NotImplementedError
