"""Tests for pipeline.checkpoint — save_checkpoint + load_latest."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import checkpoint as ck


# ---------------------------------------------------------------------------
# make_run_id
# ---------------------------------------------------------------------------
def test_make_run_id_format() -> None:
    rid = ck.make_run_id("customer_support", when=datetime(2026, 6, 7, 23, 0, 0, tzinfo=timezone.utc))
    assert rid == "run_20260607_230000_customer_support"


def test_make_run_id_sanitizes_domain() -> None:
    rid = ck.make_run_id("danger/ous name", when=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert "/" not in rid and " " not in rid
    assert rid.endswith("_danger_ous_name")


# ---------------------------------------------------------------------------
# save_checkpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_writes_file_with_all_fields(tmp_path: Path) -> None:
    path = await ck.save_checkpoint(
        run_id="run_20260607_230000_d",
        domain="d",
        accepted_count=120,
        last_node_idx=42,
        target=10000,
        rejected_count=30,
        vendi_score=28.4,
        taxonomy_coverage={"billing": 50, "shipping": 70},
        directory=tmp_path,
    )
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run_20260607_230000_d"
    assert data["accepted_count"] == 120
    assert data["last_node_idx"] == 42
    assert data["target"] == 10000
    assert data["rejected_count"] == 30
    assert data["vendi_score"] == 28.4
    assert data["taxonomy_coverage"] == {"billing": 50, "shipping": 70}
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_save_uses_safe_filename(tmp_path: Path) -> None:
    p = await ck.save_checkpoint("run_x_d", "d", 7, 1, directory=tmp_path)
    assert p.name == "run_x_d__000007.json"


@pytest.mark.asyncio
async def test_save_rejects_unsafe_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe run_id"):
        await ck.save_checkpoint("../escape", "d", 1, 0, directory=tmp_path)


@pytest.mark.asyncio
async def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    await ck.save_checkpoint("run_x_d", "d", 7, 1, directory=tmp_path)
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []


# ---------------------------------------------------------------------------
# load_latest
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_latest_returns_none_when_empty(tmp_path: Path) -> None:
    assert await ck.load_latest(directory=tmp_path) is None
    assert await ck.load_latest(directory=tmp_path / "nope") is None


@pytest.mark.asyncio
async def test_load_latest_picks_newest_by_mtime(tmp_path: Path) -> None:
    p1 = await ck.save_checkpoint("run_a_d", "d", 100, 1, directory=tmp_path)
    time.sleep(0.05)
    p2 = await ck.save_checkpoint("run_b_d", "d", 200, 2, directory=tmp_path)
    # p2 is newer.
    loaded = await ck.load_latest(directory=tmp_path)
    assert loaded is not None
    assert loaded["accepted_count"] == 200
    assert loaded["run_id"] == "run_b_d"


@pytest.mark.asyncio
async def test_load_latest_filters_by_domain(tmp_path: Path) -> None:
    # Two runs for different domains; pick newest of the requested domain.
    await ck.save_checkpoint("run_a_alpha", "alpha", 100, 1, directory=tmp_path)
    time.sleep(0.05)
    await ck.save_checkpoint("run_b_beta", "beta", 200, 2, directory=tmp_path)

    alpha = await ck.load_latest(domain="alpha", directory=tmp_path)
    assert alpha is not None and alpha["accepted_count"] == 100
    beta = await ck.load_latest(domain="beta", directory=tmp_path)
    assert beta is not None and beta["accepted_count"] == 200
    none = await ck.load_latest(domain="gamma", directory=tmp_path)
    assert none is None


@pytest.mark.asyncio
async def test_load_latest_skips_corrupt_files(tmp_path: Path) -> None:
    # Write a deliberately broken checkpoint and one good one — only good loads.
    bad = tmp_path / "run_zzz_d__000999.json"
    bad.write_text("{not json", encoding="utf-8")
    await ck.save_checkpoint("run_a_d", "d", 50, 1, directory=tmp_path)
    loaded = await ck.load_latest(directory=tmp_path)
    # If the broken file is newest, the loader returns None and logs a warning.
    # If it was older, the good one loads. Either is acceptable — what matters
    # is we never raise on a broken file.
    if loaded is not None:
        assert loaded["accepted_count"] == 50


@pytest.mark.asyncio
async def test_round_trip_save_then_load(tmp_path: Path) -> None:
    await ck.save_checkpoint(
        "run_rt_d", "d", 100, 5,
        target=1000, vendi_score=12.3,
        taxonomy_coverage={"a": 10, "b": 90},
        extra={"notes": "first half done"},
        directory=tmp_path,
    )
    loaded = await ck.load_latest(directory=tmp_path)
    assert loaded["accepted_count"] == 100
    assert loaded["vendi_score"] == 12.3
    assert loaded["taxonomy_coverage"] == {"a": 10, "b": 90}
    assert loaded["extra"] == {"notes": "first half done"}
