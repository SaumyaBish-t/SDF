"""Checkpoint manager — writes/reads run progress every 100 accepted examples.

Checkpoint file fields: accepted_count, last_node_idx, vendi_score, timestamp.
On startup the orchestrator calls `load_latest` to resume.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def save_checkpoint(accepted_count: int, last_node_idx: int, vendi_score: float) -> Path:
    raise NotImplementedError


def load_latest() -> Optional[dict]:
    raise NotImplementedError
