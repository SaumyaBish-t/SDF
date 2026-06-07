"""Checkpoint manager — save/load run progress every CHECKPOINT_INTERVAL accepts.

Format and resume semantics per PROJECT_SPEC §10. One file per checkpoint
named `run_{run_id}_{accepted_count:06d}.json` so:
  - `load_latest(domain)` can pick by mtime
  - each save is its own file (crash-safe; never overwrite the last good one)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config


_log = logging.getLogger("sdf.checkpoint")

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_\-:]+$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_run_id(domain: str, when: Optional[datetime] = None) -> str:
    """Build a stable run_id: `run_{YYYYmmdd_HHMMSS}_{domain}`."""
    ts = (when or _utc_now()).strftime("%Y%m%d_%H%M%S")
    safe_domain = re.sub(r"[^A-Za-z0-9_\-]", "_", domain) or "unknown"
    return f"run_{ts}_{safe_domain}"


def _ckpt_dir(directory: Optional[Path]) -> Path:
    return directory if directory is not None else config.CHECKPOINT_DIR


def _filename(run_id: str, accepted_count: int) -> str:
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"unsafe run_id: {run_id!r}")
    return f"{run_id}__{accepted_count:06d}.json"


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------
def _save_sync(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: stage as .tmp, then rename.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


async def save_checkpoint(
    run_id: str,
    domain: str,
    accepted_count: int,
    last_node_idx: int,
    *,
    target: Optional[int] = None,
    rejected_count: int = 0,
    vendi_score: Optional[float] = None,
    taxonomy_coverage: Optional[dict[str, int]] = None,
    extra: Optional[dict[str, Any]] = None,
    directory: Optional[Path] = None,
) -> Path:
    """Write one checkpoint file. Returns the path on success.

    Atomic via stage-then-rename. The orchestrator calls this every
    `config.CHECKPOINT_INTERVAL` accepted examples.
    """
    payload: dict[str, Any] = {
        "run_id":             run_id,
        "domain":             domain,
        "target":             target,
        "accepted_count":     accepted_count,
        "rejected_count":     rejected_count,
        "last_node_idx":      last_node_idx,
        "vendi_score":        vendi_score,
        "taxonomy_coverage":  taxonomy_coverage or {},
        "timestamp":          _utc_now().isoformat(),
    }
    if extra:
        payload["extra"] = extra

    path = _ckpt_dir(directory) / _filename(run_id, accepted_count)
    await asyncio.to_thread(_save_sync, path, payload)
    _log.info(
        "checkpoint saved: %s (accepted=%d last_node_idx=%d)",
        path.name, accepted_count, last_node_idx,
    )
    return path


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------
def _load_sync(directory: Path, domain: Optional[str]) -> Optional[dict]:
    if not directory.exists():
        return None
    candidates = list(directory.glob("run_*.json"))
    if domain:
        candidates = [p for p in candidates if p.stem.endswith(f"_{domain}") or _matches_domain(p, domain)]
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _log.warning("checkpoint file %s is corrupt — ignoring", latest)
        return None


def _matches_domain(path: Path, domain: str) -> bool:
    """Filename format is `run_{ts}_{domain}__{count}.json`."""
    stem = path.stem
    try:
        head, _ = stem.split("__", 1)
    except ValueError:
        return False
    return head.endswith(f"_{domain}")


async def load_latest(
    domain: Optional[str] = None, directory: Optional[Path] = None
) -> Optional[dict]:
    """Return the newest checkpoint (optionally filtered by domain), or None."""
    return await asyncio.to_thread(_load_sync, _ckpt_dir(directory), domain)
